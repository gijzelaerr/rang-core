//! New casacore tables (research/e4-table-create.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! `create_table` makes a table from a description and a data-manager list
//! as casacore 3.8.1's `SetupNewTable` and `Table(newtab, nrow)` do: the
//! directory, `table.lock` with the write lock, the managers (bound ones
//! from the list in its order, then one per data-manager group of the
//! unbound columns, in column order), and on the first flush `table.dat`,
//! `table.info` and the sync record (through E3's `TableWriter`, which the
//! call returns). `default_ms` makes a MeasurementSet as python-casacore's
//! `default_ms` does (`MeasurementSet::createDefaultSubtables`), from the
//! required descriptions in `ms_schema`. The format was read in the
//! casacore sources; nothing is copied from casacore (LGPL-2.1-or-later).

use std::path::{Path, PathBuf};

use crate::aipsio::{KeywordValue, Record, tp};
use crate::ms::{MsError, Result};
use crate::ms_desc::{ColBinding, ColDesc, TableDat, column_class};
use crate::ms_write::{LOCK_REQUESTS, LockFile, NewMgr, TableWriter, table_info_text};

fn err<T>(message: impl Into<String>) -> Result<T> {
    Err(MsError(message.into()))
}

// ---------------------------------------------------------------------------
// Static descriptions (the required MS and NewCalTable descriptions).

/// A keyword value in a static description.
#[derive(Clone, Copy, Debug)]
pub enum Kw {
    S(&'static str),
    Sa(&'static [&'static str]),
    F(f32),
    D(f64),
    I(i32),
    Ua(&'static [u32]),
    R(&'static [KwDef]),
    T(&'static str),
}

/// A keyword: name, value and the field comment.
#[derive(Clone, Copy, Debug)]
pub struct KwDef {
    pub name: &'static str,
    pub value: Kw,
    pub comment: &'static str,
}

pub const fn k(name: &'static str, value: Kw, comment: &'static str) -> KwDef {
    KwDef {
        name,
        value,
        comment,
    }
}

/// A column of a static description.
#[derive(Clone, Copy, Debug)]
pub struct ColDef {
    pub name: &'static str,
    pub dtype: i32,
    pub array: bool,
    pub ndim: i32,
    pub shape: &'static [i64],
    pub option: i32,
    pub dm: &'static str,
    pub group: &'static str,
    pub comment: &'static str,
    pub keywords: &'static [KwDef],
}

/// A static table description.
#[derive(Clone, Copy, Debug)]
pub struct TableDef {
    pub name: &'static str,
    pub version: &'static str,
    pub comment: &'static str,
    pub keywords: &'static [KwDef],
    pub columns: &'static [ColDef],
}

/// A record from static keywords, fields defined in order as casacore's
/// `TableRecord::define` does (variable sub-records, arrays of shape [-1]).
pub fn keywords_record(defs: &[KwDef]) -> Result<Record> {
    let mut r = Record::default();
    for d in defs {
        let value = match d.value {
            Kw::S(s) => KeywordValue::String(s.into()),
            Kw::Sa(v) => KeywordValue::StringArray(
                vec![v.len() as i64],
                v.iter().map(|s| s.to_string()).collect(),
            ),
            Kw::F(v) => KeywordValue::Scalar(tp::FLOAT, v.to_ne_bytes().to_vec()),
            Kw::D(v) => KeywordValue::Scalar(tp::DOUBLE, v.to_ne_bytes().to_vec()),
            Kw::I(v) => KeywordValue::Scalar(tp::INT, v.to_ne_bytes().to_vec()),
            Kw::Ua(v) => KeywordValue::Array(
                tp::UINT,
                vec![v.len() as i64],
                v.iter().flat_map(|x| x.to_ne_bytes()).collect(),
            ),
            Kw::R(_) => KeywordValue::Record,
            Kw::T(name) => KeywordValue::Table(name.into()),
        };
        r.define(d.name, value)?;
        if let Kw::R(sub) = d.value {
            *r.subrecord_mut(d.name)? = keywords_record(sub)?;
        }
        if !d.comment.is_empty() {
            r.set_comment(d.name, d.comment)?;
        }
    }
    Ok(r)
}

impl ColDef {
    /// The column description casacore stores for this column.
    pub fn desc(&self) -> Result<ColDesc> {
        new_coldesc(&NewColumn {
            name: self.name.into(),
            dtype: self.dtype,
            array: self.array,
            ndim: self.ndim,
            shape: self.shape.to_vec(),
            option: self.option,
            max_length: 0,
            comment: self.comment.into(),
            dm_type: self.dm.into(),
            dm_group: self.group.into(),
            keywords: keywords_record(self.keywords)?,
        })
    }
}

impl TableDef {
    pub fn columns(&self) -> Result<Vec<ColDesc>> {
        self.columns.iter().map(ColDef::desc).collect()
    }

    pub fn column(&self, name: &str) -> Option<&ColDef> {
        self.columns.iter().find(|c| c.name == name)
    }
}

// ---------------------------------------------------------------------------
// Table specifications.

/// A column of a new table (python-casacore's `makescacoldesc` and
/// `makearrcoldesc`, shapes in casacore order).
#[derive(Clone, Debug)]
pub struct NewColumn {
    pub name: String,
    pub dtype: i32,
    pub array: bool,
    /// Array dimensionality (-1 or 0: any).
    pub ndim: i32,
    /// Fixed cell shape (casacore order); empty if not fixed.
    pub shape: Vec<i64>,
    /// `ColumnDesc` options: 1 Direct, 4 FixedShape.
    pub option: i32,
    pub max_length: u32,
    pub comment: String,
    /// Data-manager type and group (empty: `StandardStMan`, the type).
    pub dm_type: String,
    pub dm_group: String,
    pub keywords: Record,
}

/// The `ColDesc` of a new column (default values zero, as python-casacore
/// writes them).
pub fn new_coldesc(c: &NewColumn) -> Result<ColDesc> {
    let dm_type = if c.dm_type.is_empty() {
        "StandardStMan".to_string()
    } else {
        c.dm_type.clone()
    };
    let dm_group = if c.dm_group.is_empty() {
        dm_type.clone()
    } else {
        c.dm_group.clone()
    };
    let derived = if c.array {
        vec![0]
    } else {
        match c.dtype {
            tp::STRING => vec![0; 4],
            code => vec![0; tp::scalar_size(code)],
        }
    };
    if !c.array && derived.is_empty() {
        return err(format!(
            "column {} has an unsupported type {}",
            c.name, c.dtype
        ));
    }
    let mut option = c.option;
    if c.array && (!c.shape.is_empty() || option & 1 != 0) {
        option |= 4;
    }
    Ok(ColDesc {
        class: column_class(c.dtype, c.array)?,
        name: c.name.clone(),
        comment: c.comment.clone(),
        dm_type,
        dm_group,
        dtype: c.dtype,
        option,
        ndim: if c.array && c.ndim == 0 && !c.shape.is_empty() {
            c.shape.len() as i32
        } else {
            c.ndim
        },
        shape: c.array.then(|| c.shape.clone()),
        max_length: c.max_length,
        keywords: c.keywords.clone(),
        derived,
    })
}

/// A data manager given for a new table (an entry of python-casacore's
/// `dminfo`).
#[derive(Clone, Debug, Default)]
pub struct ManagerSpec {
    /// `StandardStMan`, `TiledColumnStMan` or `TiledShapeStMan`; the
    /// others are refused (E5).
    pub kind: String,
    pub name: String,
    pub columns: Vec<String>,
    /// StandardStMan SPEC: BUCKETSIZE, BUCKETROWS, PERSCACHESIZE (0: not
    /// given).
    pub bucket_size: u32,
    pub bucket_rows: u32,
    pub cache: u32,
    /// Tiled SPEC DEFAULTTILESHAPE, casacore order (cell axes, then rows).
    pub tile: Vec<i64>,
    /// IncrementalStMan made by its C++ constructor (as
    /// `createDefaultSubtables` makes POINTING's): the bucket size is
    /// computed by `ISMBase::init` when none is given; from a SPEC it is
    /// 32768 by default.
    pub ism_computed: bool,
}

/// A new table: its description, data managers and `table.info`.
#[derive(Clone, Debug, Default)]
pub struct TableSpec {
    pub desc_name: String,
    pub desc_version: String,
    pub desc_comment: String,
    pub keywords: Record,
    pub columns: Vec<ColDesc>,
    /// Bound data managers, in `dminfo` order; unbound columns get one
    /// manager per group.
    pub managers: Vec<ManagerSpec>,
    /// `table.info`: type, subtype, readme.
    pub info: (String, String, String),
    /// Refused (E5): big-endian tables and MultiFile storage.
    pub big_endian: bool,
    pub multifile: bool,
}

const E6_MANAGERS: [&str; 1] = ["TiledCellStMan"];

fn check_manager_kind(kind: &str) -> Result<()> {
    match kind {
        "StandardStMan" | "TiledColumnStMan" | "TiledShapeStMan" | "IncrementalStMan"
        | "MemoryStMan" | "TiledDataStMan" => Ok(()),
        k if E6_MANAGERS.contains(&k) => err(format!("{k} tables are not created (E6)")),
        k => err(format!("data manager {k} is not created (E6)")),
    }
}

/// One resolved data manager of a new table.
struct Resolved {
    spec: ManagerSpec,
    columns: Vec<usize>,
}

/// Bound managers in the given order, then one per (type, group) of the
/// unbound columns in column order (`SetupNewTable::bindCreate`, then
/// `handleUnbound`).
fn resolve(spec: &TableSpec) -> Result<Vec<Resolved>> {
    let mut bound = vec![None::<usize>; spec.columns.len()];
    let mut out = Vec::new();
    for m in &spec.managers {
        let mut columns = Vec::new();
        for name in &m.columns {
            let i = spec
                .columns
                .iter()
                .position(|c| &c.name == name)
                .ok_or_else(|| MsError(format!("data manager {}: no column {name}", m.name)))?;
            if bound[i].is_some() {
                // A later binding wins (`bindColumn` after `bindAll`).
                let prev = bound[i].unwrap();
                let r: &mut Resolved = &mut out[prev];
                r.columns.retain(|&c| c != i);
            }
            bound[i] = Some(out.len());
            columns.push(i);
        }
        out.push(Resolved {
            spec: m.clone(),
            columns,
        });
    }
    for (i, c) in spec.columns.iter().enumerate() {
        if bound[i].is_some() {
            continue;
        }
        let at = out.iter().position(|r| {
            r.spec.kind == c.dm_type && r.spec.name == c.dm_group && r.spec.columns.is_empty()
        });
        match at {
            Some(j) => out[j].columns.push(i),
            None => out.push(Resolved {
                spec: ManagerSpec {
                    kind: c.dm_type.clone(),
                    name: c.dm_group.clone(),
                    ..Default::default()
                },
                columns: vec![i],
            }),
        }
    }
    for r in &mut out {
        r.columns.sort_unstable();
    }
    out.retain(|r| !r.columns.is_empty());
    Ok(out)
}

/// The binding casacore stores for a column (`PlainColumn`): its manager
/// and, for an array, the fixed shape.
fn binding(c: &ColDesc, seq: u32) -> ColBinding {
    let fixed =
        c.is_array() && c.option & 4 != 0 && c.shape.as_ref().is_some_and(|s| !s.is_empty());
    ColBinding {
        original_name: c.name.clone(),
        seq,
        shape: c
            .is_array()
            .then(|| fixed.then(|| c.shape.clone().unwrap())),
    }
}

/// Create `table.lock` (casacore writes the request list, then the sync
/// record on the first flush) and take the write lock.
fn new_lock(dir: &Path) -> Result<LockFile> {
    std::fs::write(dir.join("table.lock"), vec![0u8; LOCK_REQUESTS + 4])?;
    LockFile::acquire(dir, 1, std::time::Duration::ZERO)
}

/// Make the table directory, deleting a table that is there (`Table::New`).
fn new_dir(path: &Path) -> Result<PathBuf> {
    if path.join("table.dat").is_file() {
        std::fs::remove_dir_all(path)?;
    } else if path.exists() {
        return err(format!(
            "{} exists and is not a table; not overwritten",
            path.display()
        ));
    }
    std::fs::create_dir_all(path)?;
    Ok(path.to_path_buf())
}

/// Create a table with `nrows` rows (not initialised) and return it open
/// for writing. Refused with an E5 error: IncrementalStMan, MemoryStMan,
/// TiledDataStMan and other managers, a variable-shape tiled column,
/// big-endian and MultiFile tables.
pub fn create_table(path: impl AsRef<Path>, spec: &TableSpec, nrows: u64) -> Result<TableWriter> {
    create(path.as_ref(), spec, nrows)
}

fn create(path: &Path, spec: &TableSpec, nrows: u64) -> Result<TableWriter> {
    if cfg!(target_endian = "big") {
        return err("writing tables on a big-endian host is not supported (E5)");
    }
    if spec.big_endian {
        return err("big-endian tables are not created (E5)");
    }
    if spec.multifile {
        return err("MultiFile tables are not created (E5)");
    }
    let mut names = std::collections::BTreeSet::new();
    for c in &spec.columns {
        if !names.insert(c.name.as_str()) {
            return err(format!("column {} is given twice", c.name));
        }
    }
    let resolved = resolve(spec)?;
    for r in &resolved {
        check_manager_kind(&r.spec.kind)?;
        if r.spec.kind == "MemoryStMan" || r.spec.kind == "TiledDataStMan" {
            return err(format!("{} tables are not created yet (E5)", r.spec.kind));
        }
        if r.spec.kind.starts_with("Tiled") {
            for &i in &r.columns {
                let c = &spec.columns[i];
                if !c.is_array()
                    || c.option & 4 == 0
                    || c.shape.as_ref().is_none_or(|s| s.is_empty())
                {
                    return err(format!(
                        "{}: variable-shape tiled columns are not created (E5)",
                        c.name
                    ));
                }
            }
        }
    }
    let mut names = std::collections::BTreeSet::new();
    for r in &resolved {
        if !names.insert(r.spec.name.as_str()) {
            return err(format!("data manager name {} is used twice", r.spec.name));
        }
    }
    let dir = new_dir(path)?;
    let lock = new_lock(&dir)?;
    let mut bindings: Vec<ColBinding> = spec.columns.iter().map(|c| binding(c, 0)).collect();
    let mut managers = Vec::new();
    let mut blobs = Vec::new();
    let mut mgrs = Vec::new();
    for (seq, r) in resolved.iter().enumerate() {
        let seq = seq as u32;
        for &i in &r.columns {
            bindings[i].seq = seq;
        }
        let cols: Vec<(ColDesc, ColBinding)> = r
            .columns
            .iter()
            .map(|&i| (spec.columns[i].clone(), bindings[i].clone()))
            .collect();
        match r.spec.kind.as_str() {
            "StandardStMan" => {
                let (m, blob) = NewMgr::standard(
                    &dir,
                    seq,
                    &r.spec.name,
                    &cols,
                    nrows,
                    r.spec.bucket_rows,
                    r.spec.bucket_size,
                    r.spec.cache,
                )?;
                mgrs.push(m);
                blobs.push(blob);
            }
            "TiledColumnStMan" | "TiledShapeStMan" => {
                let cell = cols[0].0.shape.clone().unwrap_or_default();
                if cols.iter().any(|(c, _)| c.shape.as_ref() != Some(&cell)) {
                    return err(format!(
                        "{}: the columns of a tiled manager need one cell shape",
                        r.spec.name
                    ));
                }
                let m = NewMgr::tiled(
                    &dir,
                    seq,
                    r.spec.kind == "TiledColumnStMan",
                    &r.spec.name,
                    cols.iter().map(|(c, _)| c.dtype).collect(),
                    cell,
                    r.spec.tile.clone(),
                    nrows,
                )?;
                mgrs.push(m);
                blobs.push(Vec::new());
            }
            "IncrementalStMan" => {
                let size = if r.spec.bucket_size > 0 {
                    r.spec.bucket_size
                } else if r.spec.ism_computed {
                    0
                } else {
                    32768
                };
                let (m, blob) = NewMgr::ism(
                    &dir,
                    seq,
                    &r.spec.name,
                    &cols,
                    nrows,
                    size,
                    r.spec.cache,
                    spec.big_endian,
                )?;
                mgrs.push(m);
                blobs.push(blob);
            }
            other => return err(format!("data manager {other} is not created (E5)")),
        }
        managers.push((r.spec.kind.clone(), seq));
    }
    let dat = TableDat {
        nrows,
        little_endian: true,
        desc_name: spec.desc_name.clone(),
        desc_version: spec.desc_version.clone(),
        desc_comment: spec.desc_comment.clone(),
        keywords: spec.keywords.clone(),
        private_keywords: Record::default(),
        columns: spec.columns.clone(),
        set_version: -2,
        storage: (0, 0),
        seq_count: resolved.len() as u32,
        managers,
        bindings,
        blobs,
    };
    let (kind, sub_kind, readme) = &spec.info;
    Ok(TableWriter::from_new(
        dir,
        lock,
        dat,
        mgrs,
        table_info_text(kind, sub_kind, readme),
    ))
}

// ---------------------------------------------------------------------------
// default_ms.

/// The default subtables of `MeasurementSet::createDefaultSubtables`, in
/// its order.
pub const DEFAULT_SUBTABLES: [&str; 12] = [
    "ANTENNA",
    "DATA_DESCRIPTION",
    "FEED",
    "FLAG_CMD",
    "FIELD",
    "HISTORY",
    "OBSERVATION",
    "POINTING",
    "POLARIZATION",
    "PROCESSOR",
    "SPECTRAL_WINDOW",
    "STATE",
];

/// The required description of an MS table ("MAIN" or a subtable name).
pub fn ms_table_def(name: &str) -> Result<&'static TableDef> {
    use crate::ms_schema::*;
    Ok(match name {
        "" | "MAIN" => &MS_MAIN,
        "ANTENNA" => &MS_ANTENNA,
        "DATA_DESCRIPTION" => &MS_DATA_DESCRIPTION,
        "FEED" => &MS_FEED,
        "FIELD" => &MS_FIELD,
        "FLAG_CMD" => &MS_FLAG_CMD,
        "HISTORY" => &MS_HISTORY,
        "OBSERVATION" => &MS_OBSERVATION,
        "POINTING" => &MS_POINTING,
        "POLARIZATION" => &MS_POLARIZATION,
        "PROCESSOR" => &MS_PROCESSOR,
        "SOURCE" => &MS_SOURCE,
        "SPECTRAL_WINDOW" => &MS_SPECTRAL_WINDOW,
        "STATE" => &MS_STATE,
        other => return err(format!("MS subtable {other} is not described (E5)")),
    })
}

/// The spec of an MS table as python-casacore's `default_ms_factory`
/// makes it: the required description with the user's columns (a user
/// column replaces a required one of its name and goes last) and the
/// user's data managers; POINTING binds everything but ANTENNA_ID to an
/// IncrementalStMan `ISMPointing` and ANTENNA_ID to a StandardStMan
/// `SSMPointing` of 32768-byte buckets.
pub fn ms_table_spec(name: &str, extra: &[ColDesc], managers: &[ManagerSpec]) -> Result<TableSpec> {
    let def = ms_table_def(name)?;
    let mut columns = def.columns()?;
    for c in extra {
        columns.retain(|x| x.name != c.name);
        columns.push(c.clone());
    }
    let mut keywords = keywords_record(def.keywords)?;
    // Subtable links are made by `createDefaultSubtables`, not described.
    let links: Vec<String> = keywords
        .desc
        .fields
        .iter()
        .filter(|f| f.dtype == tp::TABLE)
        .map(|f| f.name.clone())
        .collect();
    for l in links {
        keywords.remove(&l)?;
    }
    let mut spec = TableSpec {
        desc_name: def.name.into(),
        desc_version: def.version.into(),
        desc_comment: def.comment.into(),
        keywords,
        columns,
        managers: managers.to_vec(),
        info: if matches!(name, "" | "MAIN") {
            (
                "Measurement Set".into(),
                String::new(),
                "This is a MeasurementSet Table holding measurements from a Telescope\n".into(),
            )
        } else {
            Default::default()
        },
        ..Default::default()
    };
    if name == "POINTING" && managers.is_empty() {
        spec.managers = vec![
            ManagerSpec {
                kind: "IncrementalStMan".into(),
                name: "ISMPointing".into(),
                columns: spec.columns.iter().map(|c| c.name.clone()).collect(),
                ism_computed: true,
                ..Default::default()
            },
            ManagerSpec {
                kind: "StandardStMan".into(),
                name: "SSMPointing".into(),
                columns: vec!["ANTENNA_ID".into()],
                bucket_size: 32768,
                ..Default::default()
            },
        ];
    }
    Ok(spec)
}

/// python-casacore's `default_ms_subtable(name, path, desc, dminfo)`: one
/// MS table (0 rows) at `path`, returned open for writing.
pub fn default_ms_subtable(
    name: &str,
    path: impl AsRef<Path>,
    extra: &[ColDesc],
    managers: &[ManagerSpec],
) -> Result<TableWriter> {
    let spec = ms_table_spec(name, extra, managers)?;
    create(path.as_ref(), &spec, 0)
}

/// python-casacore's `default_ms(path, desc, dminfo)`: MAIN with the
/// user's columns and managers, then the default subtables, each closed
/// when MAIN is (here: closed after its creation, which writes the same
/// files), the links defined on MAIN; MAIN is returned open for writing.
pub fn default_ms(
    path: impl AsRef<Path>,
    extra: &[ColDesc],
    managers: &[ManagerSpec],
) -> Result<TableWriter> {
    let path = path.as_ref();
    let spec = ms_table_spec("MAIN", extra, managers)?;
    let mut main = create(path, &spec, 0)?;
    for name in DEFAULT_SUBTABLES {
        let sub = default_ms_subtable(name, path.join(name), &[], &[])?;
        sub.close()?;
        main.put_keyword(None, &[name], KeywordValue::Table(format!("././{name}")))?;
    }
    Ok(main)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unbound_columns_get_one_manager_per_group() {
        let col = |name: &str, group: &str| {
            new_coldesc(&NewColumn {
                name: name.into(),
                dtype: tp::INT,
                array: false,
                ndim: 0,
                shape: Vec::new(),
                option: 0,
                max_length: 0,
                comment: String::new(),
                dm_type: String::new(),
                dm_group: group.into(),
                keywords: Record::default(),
            })
            .unwrap()
        };
        let spec = TableSpec {
            columns: vec![col("A", ""), col("B", "G"), col("C", "")],
            ..Default::default()
        };
        let r = resolve(&spec).unwrap();
        assert_eq!(r.len(), 2);
        assert_eq!(r[0].spec.name, "StandardStMan");
        assert_eq!(r[0].columns, vec![0, 2]);
        assert_eq!(r[1].spec.name, "G");
    }

    #[test]
    fn e6_managers_are_refused() {
        for kind in ["TiledCellStMan", "Adios2StMan"] {
            let e = check_manager_kind(kind).unwrap_err();
            assert!(e.0.contains("E6"), "{e:?}");
        }
        check_manager_kind("IncrementalStMan").unwrap();
    }

    #[test]
    fn ms_descriptions_build() {
        for name in DEFAULT_SUBTABLES.iter().chain(&["MAIN", "SOURCE"]) {
            let spec = ms_table_spec(name, &[], &[]).unwrap();
            assert!(!spec.columns.is_empty());
        }
    }
}
