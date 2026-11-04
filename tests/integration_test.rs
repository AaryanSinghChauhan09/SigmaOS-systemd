use anyhow::Result;
use sigmaos_component::{Config, Service, SystemdServiceManager};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_config_default_aaa() -> Result<()> {
        // Arrange & Act
        let config = Config::default();
        // Assert
        assert!(config.process().is_ok());
        Ok(())
    }

    #[test]
    fn test_service_lifecycle_aaa() -> Result<()> {
        // Arrange
        let config = Config::default();
        let mut service = Service::new(config);
        // Act
        assert!(!service.is_running());
        service.start()?;
        // Assert
        assert!(service.is_running());
        service.stop()?;
        assert!(!service.is_running());
        Ok(())
    }

    #[test]
    fn test_systemd_service_manager_aaa() {
        // Arrange & Act
        let manager = SystemdServiceManager::new();
        // Assert
        assert!(manager.list_services().is_empty());
    }
}
