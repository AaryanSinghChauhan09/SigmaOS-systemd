// SPDX-License-Identifier: Apache-2.0
//! SigmaOS-systemd — SigmaOS systemd component inspired by Linux Mint / Omarchy / Arch Linux.
//!
//! systemd-style unit file model: sectioned key=value, fail-fast validation, deterministic render.
//! Principles: single responsibility, fail-fast, defensive programming,
//! component isolation, stable API, deterministic tests.

#![forbid(unsafe_code)]

use std::fmt;
use std::collections::BTreeMap;

/// Errors for `UnitError` operations. Fail-fast: invalid input is rejected.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum UnitError {
    /// Unknown or empty unit section name
    BadSection(String),
    /// Unit key must not be empty
    EmptyKey,
    /// Unit name must end in a known suffix (.service/.socket/...)
    BadUnitName(String),
    /// Required section is absent
    MissingSection(String),
}

impl fmt::Display for UnitError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::BadSection(x) => write!(f, "unknown or empty unit section name: {x}"),
            Self::EmptyKey => write!(f, "unit key must not be empty"),
            Self::BadUnitName(x) => write!(f, "unit name must end in a known suffix (.service/.socket/...): {x}"),
            Self::MissingSection(x) => write!(f, "required section is absent: {x}"),
        }
    }
}

impl std::error::Error for UnitError {}

/// Sections valid in a systemd-style unit file.
pub const SECTIONS: &[&str] =
    &["Unit", "Service", "Socket", "Install", "Mount", "Automount", "Timer", "Path", "Slice"];

/// Suffixes that make a valid unit file name.
pub const UNIT_SUFFIXES: &[&str] =
    &[".service", ".socket", ".timer", ".mount", ".automount", ".path", ".slice", ".target", ".scope"];

/// A sectioned unit file (systemd/OpenRC/rc.d style `key = value`).
#[derive(Debug, Default)]
pub struct UnitFile {
    sections: BTreeMap<String, BTreeMap<String, String>>,
}

impl UnitFile {
    /// Empty unit file.
    pub fn new() -> Self { Self::default() }

    /// Add `key = value` under `section`; fails on unknown section or empty key.
    pub fn set(&mut self, section: &str, key: &str, value: impl Into<String>)
        -> Result<(), UnitError>
    {
        if !SECTIONS.contains(&section) {
            return Err(UnitError::BadSection(section.to_string()));
        }
        if key.trim().is_empty() { return Err(UnitError::EmptyKey); }
        self.sections
            .entry(section.to_string())
            .or_default()
            .insert(key.to_string(), value.into());
        Ok(())
    }

    /// Convenience: set a key in `[Unit]`.
    pub fn unit(&mut self, key: &str, value: impl Into<String>) -> Result<(), UnitError> {
        self.set("Unit", key, value)
    }

    /// Convenience: set a key in `[Service]`.
    pub fn service(&mut self, key: &str, value: impl Into<String>) -> Result<(), UnitError> {
        self.set("Service", key, value)
    }

    /// Convenience: set a key in `[Install]`.
    pub fn install(&mut self, key: &str, value: impl Into<String>) -> Result<(), UnitError> {
        self.set("Install", key, value)
    }

    /// Get a value; `None` if section/key absent.
    pub fn get(&self, section: &str, key: &str) -> Option<&str> {
        self.sections.get(section)?.get(key).map(String::as_str)
    }

    /// Validate: `[Unit]` present with a `Description`, and unit name is valid.
    pub fn validate(&self, unit_name: &str) -> Result<(), UnitError> {
        if !UNIT_SUFFIXES.iter().any(|s| unit_name.ends_with(s)) {
            return Err(UnitError::BadUnitName(unit_name.to_string()));
        }
        let unit = self.sections.get("Unit")
            .ok_or_else(|| UnitError::MissingSection("Unit".into()))?;
        if unit.get("Description").map_or(true, |d| d.trim().is_empty()) {
            return Err(UnitError::EmptyKey);
        }
        Ok(())
    }

    /// Render deterministic unit text: sections in canonical order,
    /// keys sorted within each section.
    pub fn render(&self, unit_name: &str) -> Result<String, UnitError> {
        self.validate(unit_name)?;
        let mut order: Vec<&str> = SECTIONS.to_vec();
        order.retain(|s| self.sections.contains_key(*s));
        let mut out = format!("# SigmaOS unit: {unit_name}\n\n");
        for sec in order {
            out.push_str(&format!("[{sec}]\n"));
            let map = &self.sections[sec];
            for (k, v) in map {
                out.push_str(&format!("{k} = {v}\n"));
            }
            out.push('\n');
        }
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn build() -> Result<UnitFile, UnitError> {
        let mut u = UnitFile::new();
        u.unit("Description", "Demo service")?;
        u.unit("After", "network.target")?;
        u.service("ExecStart", "/usr/bin/demo --serve")?;
        u.service("Restart", "on-failure")?;
        u.install("WantedBy", "multi-user.target")?;
        Ok(u)
    }

    #[test]
    fn renders_unit_text() {
        let text = build().unwrap().render("demo.service").unwrap();
        assert!(text.contains("[Unit]"));
        assert!(text.contains("Description = Demo service"));
        assert!(text.contains("ExecStart = /usr/bin/demo --serve"));
        assert!(text.contains("[Install]"));
        // [Unit] must appear before [Service] before [Install]
        assert!(text.find("[Unit]").unwrap() < text.find("[Service]").unwrap());
        assert!(text.find("[Service]").unwrap() < text.find("[Install]").unwrap());
    }

    #[test]
    fn bad_section_fails() {
        let mut u = UnitFile::new();
        assert!(matches!(u.set("Foo", "k", "v"), Err(UnitError::BadSection(_))));
    }

    #[test]
    fn bad_unit_name_fails() {
        let u = build().unwrap();
        assert!(matches!(u.render("demo"), Err(UnitError::BadUnitName(_))));
        assert!(matches!(u.render("demo.timer"), Ok(_)));
    }

    #[test]
    fn missing_description_fails() {
        let mut u = UnitFile::new();
        u.unit("After", "x").unwrap();
        assert!(matches!(u.render("d.service"), Err(UnitError::EmptyKey)));
    }

    #[test]
    fn get_roundtrip() {
        let u = build().unwrap();
        assert_eq!(u.get("Service", "Restart"), Some("on-failure"));
        assert_eq!(u.get("Service", "Nope"), None);
    }

}

/// Backwards-compatible component handle (kept for existing callers/tests).
#[derive(Debug, Default)]
pub struct Component {
    name: &'static str,
}

impl Component {
    /// Create the component handle.
    pub fn new() -> Self {
        Self { name: "SigmaOS Component" }
    }
}
