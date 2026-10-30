"""A thin ipywidgets layer over the plain functions.

Every panel has an `update(**params)` method that reruns only the affected
stage and returns its figures and tables; the widgets just call `update`
and display what comes back. Scripts and tests call `update` directly
(widget callbacks never fire under `nbconvert --execute`). Results are
cached per parameter set, so moving a slider back is instant and every
rerun is deterministic.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import data, experiment, flags, gains, image


def _widgets():
    try:
        import ipywidgets
    except ImportError as exc:  # pragma: no cover - depends on the extra
        raise ImportError(
            "install the notebook extra: pip install 'rang-core[notebook]'"
        ) from exc
    return ipywidgets


def _show(items):
    from IPython.display import display

    for item in items:
        display(item)


class Panel:
    """Base: `controls()` builds widgets, `update(**params)` computes."""

    title = "panel"

    def __init__(self, ds):
        self.ds = ds
        self._cache = {}
        self._widget = None

    def controls(self):  # pragma: no cover - overridden
        return {}

    def update(self, **params):  # pragma: no cover - overridden
        raise NotImplementedError

    def _cached(self, key, compute):
        if key not in self._cache:
            self._cache[key] = compute()
        return self._cache[key]

    @property
    def widget(self):
        if self._widget is None:
            w = _widgets()
            controls = self.controls()

            def render(**params):
                result = self.update(**params)
                _show([v for k, v in result.items() if not k.startswith("_")])

            out = w.interactive_output(render, controls)
            box = w.HBox(list(controls.values()), layout=w.Layout(flex_flow="row wrap"))
            self._widget = w.VBox([w.HTML(f"<b>{self.title}</b>"), box, out])
        return self._widget

    def _ipython_display_(self):
        from IPython.display import display

        display(self.widget)


class SolvePanel(Panel):
    """Solution intervals, iteration cap and view -> gain maps and losses."""

    title = "Solve: intervals and iteration cap"

    def controls(self):
        w = _widgets()
        style = {"description_width": "initial"}
        return {
            "time_interval": w.IntSlider(
                value=2,
                min=1,
                max=8,
                description="integrations / bin",
                continuous_update=False,
                style=style,
            ),
            "freq_interval": w.Dropdown(
                options=[8, 16, 32, 64, 128, 256],
                value=32,
                description="channels / bin",
                style=style,
            ),
            "iterations": w.IntSlider(
                value=50,
                min=1,
                max=100,
                description="iteration cap",
                continuous_update=False,
                style=style,
            ),
            "quantity": w.Dropdown(
                options=list(gains.QUANTITIES), value="amplitude", description="show"
            ),
            "element": w.Dropdown(
                options=["XX", "YY", "XY", "YX"], value="XX", description="element"
            ),
            "gauge": w.Checkbox(value=True, description="polar gauge"),
        }

    def solve(self, time_interval=2, freq_interval=32, iterations=50):
        key = (int(time_interval), int(freq_interval), int(iterations))
        return self._cached(key, lambda: gains.solve(self.ds, None, *key))

    def update(
        self,
        time_interval=2,
        freq_interval=32,
        iterations=50,
        quantity="amplitude",
        element="XX",
        gauge=True,
    ):
        sol = self.solve(time_interval, freq_interval, iterations)
        return {
            "maps": gains.gain_maps(self.ds, sol, quantity, element, gauge),
            "losses": gains.losses_table(sol),
            "_solution": sol,
        }


class FlagPanel(Panel):
    """Strategy, step and baseline -> per-step table and diff waterfall."""

    title = "Flag: a Tricolour strategy step by step"

    def __init__(self, ds, library=None):
        super().__init__(ds)
        self.library = library or flags.strategy_library()

    def controls(self):
        w = _widgets()
        names = list(self.library)
        strategy = w.Dropdown(options=names, value=names[0], description="strategy")
        step = w.IntSlider(
            value=0,
            min=0,
            max=len(self.library[names[0]]) - 1,
            description="step",
            continuous_update=False,
        )

        def resize(change):
            step.max = len(self.library[change["new"]]) - 1
            step.value = min(step.value, step.max)

        strategy.observe(resize, names="value")
        pairs = self.ds.baselines()
        return {
            "strategy": strategy,
            "step": step,
            "baseline": w.Dropdown(
                options=[(self.ds.baseline_label(p), p) for p in pairs],
                value=pairs[0],
                description="baseline",
            ),
        }

    def run(self, strategy):
        return self._cached(
            strategy, lambda: flags.run_strategy(self.ds, self.library[strategy])
        )

    def update(self, strategy="teaching", step=0, baseline=None):
        run = self.run(strategy)
        step = min(int(step), len(run["strategies"]) - 1)
        return {
            "table": flags.step_table(run),
            "waterfall": flags.step_waterfall(self.ds, run, step, baseline),
            "_run": run,
        }


class ImagePanel(Panel):
    """Two flag sets, weighting and robustness -> images and their difference.

    `flag_sets` maps a label to added (row, chan) flags; the original data
    flags are always kept. With `corrected=True` each set is solved with the
    frozen settings first and the corrected data are imaged, as in the
    campaigns.
    """

    title = "Image: weighting, robustness and two flag sets"

    def __init__(self, ds, flag_sets=None, zoom=128):
        super().__init__(ds)
        none = np.zeros_like(ds.state["train"])
        self.flag_sets = flag_sets or {"original": none}
        self.zoom = zoom

    def controls(self):
        w = _widgets()
        labels = list(self.flag_sets)
        return {
            "set_a": w.Dropdown(options=labels, value=labels[0], description="A"),
            "set_b": w.Dropdown(options=labels, value=labels[-1], description="B"),
            "mode": w.Dropdown(
                options=list(image.MODES), value="briggs", description="weighting"
            ),
            "robust": w.FloatSlider(
                value=0.5,
                min=-2.0,
                max=2.0,
                step=0.25,
                description="robust",
                continuous_update=False,
            ),
            "corrected": w.Checkbox(value=True, description="gain-corrected"),
        }

    def _solution(self, label):
        params = experiment._frozen_params()
        return self._cached(
            ("solve", label),
            lambda: gains.solve(
                self.ds,
                self.flag_sets[label],
                params["time_interval"],
                params["freq_interval"],
                params["iterations"],
            ),
        )

    def image(self, label, mode="briggs", robust=0.5, corrected=True):
        key = ("image", label, mode, float(robust), bool(corrected))

        def compute():
            sol = self._solution(label) if corrected else None
            return image.image(
                self.ds, sol, added=self.flag_sets[label], mode=mode, robust=robust
            )

        return self._cached(key, compute)

    def update(self, set_a=None, set_b=None, mode="briggs", robust=0.5, corrected=True):
        labels = list(self.flag_sets)
        set_a, set_b = set_a or labels[0], set_b or labels[-1]
        a = self.image(set_a, mode, robust, corrected)
        b = self.image(set_b, mode, robust, corrected)
        names = (set_a, set_b) if set_a != set_b else (f"{set_a} (A)", f"{set_b} (B)")
        return {
            "images": image.image_figure(a, self.zoom),
            "compare": image.compare(a, b, names, self.zoom),
            "table": image.metrics_table(dict(zip(names, (a, b)))),
        }


class DecisionPanel(Panel):
    """Comparator strategy -> arms, TV loop, images and the frozen calls."""

    title = "Decide: the campaign's arms and the frozen rule"

    def __init__(self, ds, library=None):
        super().__init__(ds)
        self.library = library or flags.strategy_library()

    def controls(self):
        w = _widgets()
        names = list(self.library)
        default = (
            "caracal-calibrator-firstpass"
            if "caracal-calibrator-firstpass" in names
            else names[0]
        )
        return {
            "strategy": w.Dropdown(
                options=names, value=default, description="comparator"
            )
        }

    def run(self, strategy):
        def compute():
            arms, trials = experiment.run_arms(self.ds, self.library[strategy])
            images = experiment.image_arms(self.ds, arms)
            return arms, trials, images

        return self._cached(strategy, compute)

    def update(self, strategy="teaching"):
        arms, trials, images = self.run(strategy)
        calls = experiment.decisions(arms, images)
        return {
            "arms": experiment.arms_table(arms, images),
            "trials": experiment.trials_table(trials),
            "calls": calls,
            "ratios": experiment.ratio_figure(calls, f"comparator: {strategy}"),
        }


class LoadPanel(Panel):
    """Dataset and cache directory -> a loaded `Dataset` (with fetch progress)."""

    title = "Load"

    def __init__(self, cache_dir=None, on_load=None):
        super().__init__(None)
        self.cache_dir = Path(cache_dir) if cache_dir else data.default_cache_dir()
        self.on_load = on_load

    def update(self, dataset="fixture", cache_dir=None, progress=None):
        cache = Path(cache_dir) if cache_dir else self.cache_dir
        if dataset == "fixture":
            ds = data.load_fixture(cache_dir=cache)
        elif dataset == "luno (local copy)":
            ds = data.load_luno()
        elif dataset == "luno (fetch into cache)":
            kwargs = {"progress": progress} if progress is not None else {}
            ds = data.load_luno(cache_dir=cache, fetch=True, **kwargs)
        else:
            raise ValueError(dataset)
        self.ds = ds
        if self.on_load is not None:
            self.on_load(ds)
        return {"summary": data.summary(ds), "_dataset": ds}

    @property
    def widget(self):
        if self._widget is None:
            w = _widgets()
            choice = w.Dropdown(
                options=["fixture", "luno (local copy)", "luno (fetch into cache)"],
                description="dataset",
            )
            cache = w.Text(value=str(self.cache_dir), description="cache dir")
            button = w.Button(description="load", button_style="primary")
            bar = w.FloatProgress(value=0.0, min=0.0, max=1.0, description="fetch")
            out = w.Output()

            def progress(done, expected, seconds):
                bar.value = min(done / expected, 1.0) if expected else 0.0
                bar.description = f"{done / 1e6:.0f} MB"

            def click(_):
                out.clear_output()
                with out:
                    result = self.update(choice.value, cache.value, progress)
                    _show([result["summary"]])

            button.on_click(click)
            self._widget = w.VBox([w.HBox([choice, cache, button]), bar, out])
        return self._widget


class Explorer:
    """All steering panels for one dataset in tabs."""

    def __init__(self, ds, flag_sets=None):
        self.ds = ds
        library = flags.strategy_library()
        self.panels = {
            "solve": SolvePanel(ds),
            "flag": FlagPanel(ds, library),
            "image": ImagePanel(ds, flag_sets),
            "decide": DecisionPanel(ds, library),
        }

    @property
    def widget(self):
        w = _widgets()
        tabs = w.Tab(children=[p.widget for p in self.panels.values()])
        for i, name in enumerate(self.panels):
            tabs.set_title(i, name)
        return tabs

    def _ipython_display_(self):
        from IPython.display import display

        display(self.widget)
