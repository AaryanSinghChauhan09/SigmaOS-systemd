// SPDX-License-Identifier: Apache-2.0
//! SigmaOS-systemd - System and service manager
//! Part of SigmaOS multi-repository architecture

#![no_std]

pub mod systemd;

pub use systemd::Systemd;
