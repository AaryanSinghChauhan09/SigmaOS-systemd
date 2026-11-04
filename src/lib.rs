// SPDX-License-Identifier: Apache-2.0
//! SigmaOS-systemd - System and service manager
//! Part of SigmaOS multi-repository architecture

pub mod config;
pub mod error;
pub mod service;
pub mod systemd;

pub use config::Config;
pub use error::{ComponentError, Result};
pub use service::Service;
pub use systemd::{
    SystemdServiceManager, SystemdServiceUnit, SystemdUnitType, SystemdServiceState,
    LogindManager, TimesyncdEngine, SystemdUnitFile,
};
