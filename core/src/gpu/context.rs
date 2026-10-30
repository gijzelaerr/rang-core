//! The process-wide wgpu adapter, device, queue and compiled pipelines,
//! created on first use and reused (their cost is reported once, as the
//! first-call cost).

use super::Precision;
use super::shader;
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Instant;

pub(crate) struct Pipelines {
    pub(crate) grid: wgpu::ComputePipeline,
    pub(crate) fft: wgpu::ComputePipeline,
    pub(crate) project: wgpu::ComputePipeline,
}

pub(crate) struct Context {
    // Kept alive for the lifetime of the device.
    _instance: wgpu::Instance,
    pub(crate) device: wgpu::Device,
    pub(crate) queue: wgpu::Queue,
    pub(crate) info: wgpu::AdapterInfo,
    pub(crate) limits: wgpu::Limits,
    pub(crate) f64: bool,
    pipelines: Mutex<[Option<Arc<Pipelines>>; 2]>,
    /// Serialises inversions: one at a time per process.
    pub(crate) busy: Mutex<()>,
}

static CONTEXT: OnceLock<Result<Arc<Context>, String>> = OnceLock::new();

/// Environment override: a case-insensitive substring of the adapter name.
pub const ADAPTER_ENV: &str = "RANG_GPU_ADAPTER";

fn rank(info: &wgpu::AdapterInfo, f64: bool) -> (u8, u8, u8) {
    let kind = match info.device_type {
        wgpu::DeviceType::DiscreteGpu => 0,
        wgpu::DeviceType::IntegratedGpu => 1,
        wgpu::DeviceType::VirtualGpu => 2,
        _ => 3,
    };
    let backend = match info.backend {
        wgpu::Backend::Vulkan => 0,
        wgpu::Backend::Metal => 1,
        wgpu::Backend::Dx12 => 2,
        _ => 3,
    };
    (kind, u8::from(!f64), backend)
}

fn create() -> Result<Arc<Context>, String> {
    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
        backends: wgpu::Backends::VULKAN | wgpu::Backends::METAL | wgpu::Backends::DX12,
        ..wgpu::InstanceDescriptor::new_without_display_handle()
    });
    let wanted = std::env::var(ADAPTER_ENV)
        .ok()
        .map(|v| v.to_lowercase())
        .filter(|v| !v.is_empty());
    let mut seen = Vec::new();
    let mut candidates = Vec::new();
    for adapter in pollster::block_on(instance.enumerate_adapters(wgpu::Backends::all())) {
        let info = adapter.get_info();
        seen.push(format!(
            "{} ({:?}, {:?})",
            info.name, info.backend, info.device_type
        ));
        // Never a software rasteriser (Microsoft Basic Render Driver,
        // lavapipe, llvmpipe).
        if info.device_type == wgpu::DeviceType::Cpu {
            continue;
        }
        if let Some(name) = &wanted
            && !info.name.to_lowercase().contains(name.as_str())
        {
            continue;
        }
        let f64 = adapter.features().contains(wgpu::Features::SHADER_F64);
        candidates.push((rank(&info, f64), adapter, info, f64));
    }
    candidates.sort_by_key(|c| c.0);
    let Some((_, adapter, info, f64)) = candidates.into_iter().next() else {
        return Err(format!(
            "no usable GPU adapter (Vulkan, Metal or DX12, not a CPU rasteriser){}; seen: [{}]",
            wanted
                .map(|w| format!(" matching {ADAPTER_ENV}={w}"))
                .unwrap_or_default(),
            seen.join("; ")
        ));
    };
    let limits = adapter.limits();
    let features = if f64 {
        wgpu::Features::SHADER_F64
    } else {
        wgpu::Features::empty()
    };
    let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor {
        label: Some("rang gridder"),
        required_features: features,
        required_limits: limits.clone(),
        ..Default::default()
    }))
    .map_err(|e| format!("requesting a device on {}: {e}", info.name))?;
    Ok(Arc::new(Context {
        _instance: instance,
        device,
        queue,
        info,
        limits,
        f64,
        pipelines: Mutex::new([None, None]),
        busy: Mutex::new(()),
    }))
}

/// The shared context and the seconds spent creating it in this call (zero
/// once it exists).
pub(crate) fn get() -> Result<(Arc<Context>, f64), String> {
    let start = Instant::now();
    let created = CONTEXT.get().is_none();
    let context = CONTEXT.get_or_init(create).clone()?;
    let seconds = if created {
        start.elapsed().as_secs_f64()
    } else {
        0.0
    };
    Ok((context, seconds))
}

/// One line naming the adapter, its backend and its f64 support.
pub fn adapter_description() -> Result<String, String> {
    let (context, _) = get()?;
    let info = &context.info;
    Ok(format!(
        "{} ({:?}, {:?}, driver {} {}; SHADER_F64 {})",
        info.name,
        info.backend,
        info.device_type,
        info.driver,
        info.driver_info,
        if context.f64 { "yes" } else { "no" }
    ))
}

impl Context {
    /// The pipelines of one precision, compiled on first use; also the
    /// seconds spent compiling in this call.
    pub(crate) fn pipelines(&self, precision: Precision) -> Result<(Arc<Pipelines>, f64), String> {
        if precision == Precision::F64 && !self.f64 {
            return Err(format!(
                "the adapter {} ({:?}) has no SHADER_F64; only the f32 path can run on it",
                self.info.name, self.info.backend
            ));
        }
        let slot = match precision {
            Precision::F64 => 0,
            Precision::F32 => 1,
        };
        let mut cache = self.pipelines.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(p) = &cache[slot] {
            return Ok((p.clone(), 0.0));
        }
        let start = Instant::now();
        let sources = shader::sources(precision);
        let make = |label: &str, source: &str, entry: &str| {
            let module = self
                .device
                .create_shader_module(wgpu::ShaderModuleDescriptor {
                    label: Some(label),
                    source: wgpu::ShaderSource::Wgsl(source.into()),
                });
            self.device
                .create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
                    label: Some(label),
                    layout: None,
                    module: &module,
                    entry_point: Some(entry),
                    compilation_options: Default::default(),
                    cache: None,
                })
        };
        let scope = self.device.push_error_scope(wgpu::ErrorFilter::Validation);
        let pipelines = Pipelines {
            grid: make("grid", &sources.grid, "grid"),
            fft: make("fft", &sources.fft, "fft_pass"),
            project: make("project", &sources.project, "project"),
        };
        if let Some(error) = pollster::block_on(scope.pop()) {
            return Err(format!("compiling the {precision:?} shaders: {error}"));
        }
        let pipelines = Arc::new(pipelines);
        cache[slot] = Some(pipelines.clone());
        Ok((pipelines, start.elapsed().as_secs_f64()))
    }
}
