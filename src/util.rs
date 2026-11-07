//! systemd model — system and service manager.

#[derive(Debug, Clone)]
pub struct Unit {
    pub name: String,
    pub type_: String,
    pub active: bool,
    pub enabled: bool,
    pub pid: Option<u32>,
}

#[derive(Debug, Clone)]
pub struct Target {
    pub name: String,
    pub units: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct Model {
    pub units: Vec<Unit>,
    pub targets: Vec<Target>,
}

impl Default for Model {
    fn default() -> Self { Self { units: vec![], targets: vec![] } }
}

impl Model {
    pub fn new() -> Self { Self::default() }

    pub fn add_unit(&mut self, name: &str, type_: &str) {
        if !self.units.iter().any(|u| u.name == name) {
            self.units.push(Unit { name: name.into(), type_: type_.into(), active: false, enabled: false, pid: None });
        }
    }

    pub fn start(&mut self, name: &str) -> bool {
        if let Some(u) = self.units.iter_mut().find(|u| u.name == name) {
            u.active = true;
            u.pid = Some(1000);
            true
        } else { false }
    }

    pub fn stop(&mut self, name: &str) -> bool {
        if let Some(u) = self.units.iter_mut().find(|u| u.name == name) {
            u.active = false;
            u.pid = None;
            true
        } else { false }
    }

    pub fn enable(&mut self, name: &str) -> bool {
        if let Some(u) = self.units.iter_mut().find(|u| u.name == name) {
            u.enabled = true;
            true
        } else { false }
    }

    pub fn list_units(&self) -> &[Unit] { &self.units }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unit_start_stop_enable() {
        let mut s = Model::new();
        s.add_unit("ssh.service", "service");
        assert!(s.start("ssh.service"));
        assert!(s.enable("ssh.service"));
        assert!(s.stop("ssh.service"));
    }
}
