//! CASA calibration tables (NewCalTable) for the table writer
//! (research/e4-table-create.md).
//!
//! Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
//! License, version 3 or (at your option) any later version; see `LICENSE`.
//!
//! The schema is the one CASA 6.7.6 writes (read from its `gaincal`
//! tables, `ms_schema::CT_MAIN`): 13 MAIN columns with CPARAM (Complex: G,
//! B, Df) or FPARAM (Float: K), one StandardStMan named `MSMTAB` whose
//! columns name type and group `StandardStMan`, the keywords `ParType`,
//! `MSName`, `VisCal`, `PolBasis`, `CASA_Version` and the subtable links,
//! `table.info` type `Calibration` with the VisCal name as subtype, and the
//! subtables OBSERVATION, ANTENNA, FIELD, SPECTRAL_WINDOW and HISTORY with
//! the MeasurementSet descriptions. CASA writes a calibration table by a
//! deep copy of its in-memory table (`NewCalTable::writeToDisk`): every
//! table is created with all its rows, filled row by row, flushed, and the
//! main table's subtable links are defined (and flushed) after the
//! subtables are written; `rang.core_ms_write.create_caltable` drives that
//! sequence with these specs. Nothing is copied from CASA.

use crate::aipsio::{KeywordValue, tp};
use crate::ms::{MsError, Result};
use crate::ms_create::{ManagerSpec, TableSpec, keywords_record, ms_table_def};
use crate::ms_schema::CT_MAIN;

/// The subtables of a calibration table, in the order CASA links them.
pub const CAL_SUBTABLES: [&str; 5] = [
    "OBSERVATION",
    "ANTENNA",
    "FIELD",
    "SPECTRAL_WINDOW",
    "HISTORY",
];

/// The data manager every calibration table and subtable has.
pub const CAL_MANAGER: &str = "MSMTAB";

/// The keywords and parameter type of a calibration table.
#[derive(Clone, Debug)]
pub struct CalTable {
    /// `G Jones`, `B Jones`, `K Jones`, `Df Jones`, ...
    pub vis_cal: String,
    /// FPARAM (Float, e.g. K) instead of CPARAM (Complex).
    pub float_param: bool,
    pub ms_name: String,
    pub pol_basis: String,
    pub casa_version: String,
}

fn one_manager(spec: &mut TableSpec) {
    spec.managers = vec![ManagerSpec {
        kind: "StandardStMan".into(),
        name: CAL_MANAGER.into(),
        columns: spec.columns.iter().map(|c| c.name.clone()).collect(),
        ..Default::default()
    }];
}

/// The spec of the MAIN table (its subtable links included, as
/// `././NAME`).
pub fn main_spec(cal: &CalTable) -> Result<TableSpec> {
    if cal.vis_cal.is_empty() {
        return Err(MsError("a calibration table needs a VisCal name".into()));
    }
    let mut columns = CT_MAIN.columns()?;
    if cal.float_param {
        let c = columns
            .iter_mut()
            .find(|c| c.name == "CPARAM")
            .ok_or_else(|| MsError("CPARAM missing from the schema".into()))?;
        *c = crate::ms_create::new_coldesc(&crate::ms_create::NewColumn {
            name: "FPARAM".into(),
            dtype: tp::FLOAT,
            array: true,
            ndim: c.ndim,
            shape: Vec::new(),
            option: c.option,
            max_length: 0,
            comment: c.comment.clone(),
            dm_type: c.dm_type.clone(),
            dm_group: c.dm_group.clone(),
            keywords: c.keywords.clone(),
        })?;
    }
    let mut keywords = keywords_record(&[])?;
    let par_type = if cal.float_param { "Float" } else { "Complex" };
    for (name, value) in [
        ("ParType", par_type),
        ("MSName", cal.ms_name.as_str()),
        ("VisCal", cal.vis_cal.as_str()),
        ("PolBasis", cal.pol_basis.as_str()),
        ("CASA_Version", cal.casa_version.as_str()),
    ] {
        keywords.define(name, KeywordValue::String(value.into()))?;
    }
    for name in CAL_SUBTABLES {
        keywords.define(name, KeywordValue::Table(format!("././{name}")))?;
    }
    let mut spec = TableSpec {
        desc_name: cal.vis_cal.clone(),
        desc_version: CT_MAIN.version.into(),
        desc_comment: CT_MAIN.comment.into(),
        keywords,
        columns,
        info: ("Calibration".into(), cal.vis_cal.clone(), String::new()),
        ..Default::default()
    };
    one_manager(&mut spec);
    Ok(spec)
}

/// The spec of a calibration subtable (the MeasurementSet description,
/// one StandardStMan `MSMTAB`, an empty `table.info` type).
pub fn subtable_spec(name: &str) -> Result<TableSpec> {
    if !CAL_SUBTABLES.contains(&name) {
        return Err(MsError(format!("{name} is not a calibration subtable")));
    }
    let def = ms_table_def(name)?;
    let mut spec = TableSpec {
        desc_name: def.name.into(),
        desc_version: def.version.into(),
        desc_comment: def.comment.into(),
        keywords: keywords_record(def.keywords)?,
        columns: def.columns()?,
        ..Default::default()
    };
    one_manager(&mut spec);
    Ok(spec)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn k_tables_have_fparam_and_float_partype() {
        let cal = CalTable {
            vis_cal: "K Jones".into(),
            float_param: true,
            ms_name: "x.ms".into(),
            pol_basis: "unknown".into(),
            casa_version: "6.7.6-14".into(),
        };
        let spec = main_spec(&cal).unwrap();
        let names: Vec<&str> = spec.columns.iter().map(|c| c.name.as_str()).collect();
        assert_eq!(names[8], "FPARAM");
        assert_eq!(spec.columns[8].dtype, tp::FLOAT);
        assert_eq!(spec.columns.len(), 13);
        assert_eq!(spec.keywords.desc.fields.len(), 10);
        assert_eq!(spec.info.1, "K Jones");
        for name in CAL_SUBTABLES {
            assert!(!subtable_spec(name).unwrap().columns.is_empty());
        }
    }
}
