"""
Unit Tests for Services Module

Tests for EmailProcessor, TaskManager, and SchedulerManager classes.
Uses pytest and arrange-act-assert model with mocked data.
"""

import pytest
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# Import services modules
from services.email_processor import EmailProcessor, ServiceState, ProcessingMode, ServiceStats
from services.task_manager import TaskManager, get_task_manager, shutdown_task_manager
from services.scheduler_manager import SchedulerManager, get_scheduler_manager, SchedulerInfo
from config import AccountConfig


class TestServiceStats:
    """Test ServiceStats dataclass"""
    
    def test_service_stats_initialization(self):
        """Test ServiceStats default initialization"""
        # Arrange & Act
        stats = ServiceStats()
        
        # Assert
        assert stats.emails_processed == 0
        assert stats.emails_pending == 0
        assert stats.last_run is None
        assert stats.total_runtime == timedelta()
        assert stats.error_count == 0
        assert stats.avg_processing_time == 0.0
        assert stats.mode_start_time is None
    
    def test_service_stats_to_dict(self):
        """Test ServiceStats to_dict conversion"""
        # Arrange
        test_time = datetime.now()
        stats = ServiceStats(
            emails_processed=100,
            emails_pending=5,
            last_run=test_time,
            error_count=2,
            avg_processing_time=1.5,
            mode_start_time=test_time
        )
        
        # Act
        stats_dict = stats.to_dict()
        
        # Assert
        assert stats_dict['emails_processed'] == 100
        assert stats_dict['emails_pending'] == 5
        assert stats_dict['last_run'] == test_time.isoformat()
        assert stats_dict['error_count'] == 2
        assert stats_dict['avg_processing_time'] == 1.5
        assert stats_dict['mode_start_time'] == test_time.isoformat()


class TestEmailProcessor:
    """Test EmailProcessor class"""
    
    @pytest.fixture
    def mock_account_config(self):
        """Create mock account configuration"""
        return AccountConfig(
            name="test_account",
            server="test.example.com",
            email="test@example.com",
            password="test_password"
        )
    
    @pytest.fixture
    def email_processor(self, mock_account_config):
        """Create EmailProcessor instance for testing"""
        with patch('services.email_processor.get_config'):
            processor = EmailProcessor(mock_account_config)
            yield processor
            # Cleanup
            if processor.scheduler.running:
                processor.scheduler.shutdown(wait=False)
    
    def test_email_processor_initialization(self, email_processor, mock_account_config):
        """Test EmailProcessor initialization"""
        # Assert
        assert email_processor.account_config == mock_account_config
        assert email_processor.state == ServiceState.STOPPED
        assert email_processor.mode == ProcessingMode.STARTUP
        assert isinstance(email_processor.stats, ServiceStats)
        assert not email_processor.scheduler.running
    
    def test_start_service_invalid_state(self, email_processor):
        """Test starting service from invalid state"""
        # Arrange
        email_processor.state = ServiceState.RUNNING_STARTUP
        
        # Act
        result = email_processor.start()
        
        # Assert
        assert not result
        assert email_processor.state == ServiceState.RUNNING_STARTUP
    
    @patch('services.email_processor.EmailProcessor._test_connection')
    def test_start_service_connection_failure(self, mock_test_connection, email_processor):
        """Test starting service with connection failure"""
        # Arrange
        mock_test_connection.return_value = False
        
        # Act
        result = email_processor.start()
        
        # Assert
        assert not result
        assert email_processor.state == ServiceState.ERROR
        assert email_processor.last_error == "Failed to connect to email server"
    
    @patch('services.email_processor.EmailProcessor._test_connection')
    @patch('services.email_processor.EmailProcessor._setup_jobs')
    @patch('services.email_processor.EmailProcessor._validate_and_setup_folders')
    def test_start_service_success(self, mock_validate_folders, mock_setup_jobs, mock_test_connection, email_processor):
        """Test successful service start"""
        # Arrange
        mock_test_connection.return_value = True
        mock_validate_folders.return_value = {'success': True}
        
        # Act
        result = email_processor.start(ProcessingMode.STARTUP)
        
        # Assert
        assert result
        assert email_processor.state == ServiceState.RUNNING_STARTUP
        assert email_processor.mode == ProcessingMode.STARTUP
        assert email_processor.scheduler.running
        mock_setup_jobs.assert_called_once()
    
    @patch('services.email_processor.EmailProcessor._test_connection')
    @patch('services.email_processor.EmailProcessor._setup_jobs')
    @patch('services.email_processor.EmailProcessor._validate_and_setup_folders')
    def test_start_service_maintenance_mode(self, mock_validate_folders, mock_setup_jobs, mock_test_connection, email_processor):
        """Test starting service in maintenance mode"""
        # Arrange
        mock_test_connection.return_value = True
        mock_validate_folders.return_value = {'success': True}
        
        # Act
        result = email_processor.start(ProcessingMode.MAINTENANCE)
        
        # Assert
        assert result
        assert email_processor.state == ServiceState.RUNNING_MAINTENANCE
        assert email_processor.mode == ProcessingMode.MAINTENANCE
    
    def test_stop_service_already_stopped(self, email_processor):
        """Test stopping already stopped service"""
        # Act
        result = email_processor.stop()
        
        # Assert
        assert result
        assert email_processor.state == ServiceState.STOPPED
    
    @patch('services.email_processor.EmailProcessor._test_connection')
    @patch('services.email_processor.EmailProcessor._setup_jobs')
    def test_stop_running_service(self, mock_setup_jobs, mock_test_connection, email_processor):
        """Test stopping running service"""
        # Arrange
        mock_test_connection.return_value = True
        email_processor.start()
        
        # Act
        result = email_processor.stop()
        
        # Assert
        assert result
        assert email_processor.state == ServiceState.STOPPED
        assert not email_processor.scheduler.running
    
    @patch('services.email_processor.EmailProcessor._test_connection')
    @patch('services.email_processor.EmailProcessor._setup_jobs')
    @patch('services.email_processor.EmailProcessor._validate_and_setup_folders')
    def test_switch_mode(self, mock_validate_folders, mock_setup_jobs, mock_test_connection, email_processor):
        """Test switching processing mode"""
        # Arrange
        mock_test_connection.return_value = True
        mock_validate_folders.return_value = {'success': True}
        email_processor.start(ProcessingMode.STARTUP)
        
        # Act
        result = email_processor.switch_mode(ProcessingMode.MAINTENANCE)
        
        # Assert
        assert result
        assert email_processor.mode == ProcessingMode.MAINTENANCE
        assert email_processor.state == ServiceState.RUNNING_MAINTENANCE
    
    def test_switch_mode_same_mode(self, email_processor):
        """Test switching to same mode"""
        # Act
        result = email_processor.switch_mode(ProcessingMode.STARTUP)
        
        # Assert
        assert result
        assert email_processor.mode == ProcessingMode.STARTUP
    
    def test_switch_mode_invalid_state(self, email_processor):
        """Test switching mode from invalid state"""
        # Arrange
        email_processor.state = ServiceState.STOPPED
        
        # Act
        result = email_processor.switch_mode(ProcessingMode.MAINTENANCE)
        
        # Assert
        assert not result
    
    def test_get_status(self, email_processor, mock_account_config):
        """Test getting service status"""
        # Act
        status = email_processor.get_status()
        
        # Assert
        assert status['account_email'] == mock_account_config.email
        assert status['state'] == ServiceState.STOPPED.value
        assert status['mode'] == ProcessingMode.STARTUP.value
        assert 'stats' in status
        assert 'scheduler_running' in status
    
    def test_test_connection_success(self, email_processor):
        """Test successful connection test"""
        # Arrange
        mock_mailbox = Mock()
        email_processor.account.login = Mock(return_value=mock_mailbox)
        
        # Act
        result = email_processor._test_connection()
        
        # Assert
        assert result
        mock_mailbox.logout.assert_called_once()
    
    def test_test_connection_failure(self, email_processor):
        """Test connection test failure"""
        # Arrange
        email_processor.account.login = Mock(side_effect=Exception("Connection failed"))
        
        # Act
        result = email_processor._test_connection()
        
        # Assert
        assert not result
    
    def test_should_transition_to_maintenance_not_startup(self, email_processor):
        """Test transition check when not in startup mode"""
        # Arrange
        email_processor.mode = ProcessingMode.MAINTENANCE
        
        # Act
        result = email_processor.should_transition_to_maintenance()
        
        # Assert
        assert not result
    
    def test_should_transition_criteria_not_met(self, email_processor):
        """Test transition when criteria not met"""
        # Arrange
        email_processor.mode = ProcessingMode.STARTUP
        email_processor.stats.emails_pending = 100  # Too many pending
        
        # Act
        result = email_processor.should_transition_to_maintenance()
        
        # Assert
        assert not result
    
    def test_should_transition_criteria_met(self, email_processor):
        """Test transition when all criteria met"""
        # Arrange
        email_processor.mode = ProcessingMode.STARTUP
        email_processor.stats.emails_pending = 30
        email_processor.stats.mode_start_time = datetime.now() - timedelta(days=15)
        email_processor.consecutive_errors = 0
        email_processor.stats.emails_processed = 1000
        email_processor.stats.error_count = 10
        
        # Act
        result = email_processor.should_transition_to_maintenance()
        
        # Assert
        assert result


class TestTaskManager:
    """Test TaskManager class"""
    
    @pytest.fixture
    def task_manager(self):
        """Create TaskManager instance for testing"""
        # Reset global task manager
        shutdown_task_manager()
        manager = TaskManager(max_workers=2)
        yield manager
        # Cleanup
        manager.shutdown()
    
    @pytest.fixture
    def mock_account_config(self):
        """Create mock account configuration"""
        return AccountConfig(
            name="test_account",
            server="test.example.com",
            email="test@example.com",
            password="test_password"
        )
    
    def test_task_manager_initialization(self, task_manager):
        """Test TaskManager initialization"""
        # Assert
        assert len(task_manager.processors) == 0
        assert task_manager.executor._max_workers == 2
        assert isinstance(task_manager.startup_time, datetime)
        assert len(task_manager.task_history) == 0
    
    def test_add_account_success(self, task_manager, mock_account_config):
        """Test successfully adding an account"""
        # Act
        result = task_manager.add_account(mock_account_config)
        
        # Assert
        assert result
        assert mock_account_config.email in task_manager.processors
        assert len(task_manager.task_history) > 0
    
    def test_add_account_duplicate(self, task_manager, mock_account_config):
        """Test adding duplicate account"""
        # Arrange
        task_manager.add_account(mock_account_config)
        
        # Act
        result = task_manager.add_account(mock_account_config)
        
        # Assert
        assert not result
        assert len(task_manager.processors) == 1
    
    def test_remove_account_success(self, task_manager, mock_account_config):
        """Test successfully removing an account"""
        # Arrange
        task_manager.add_account(mock_account_config)
        
        # Act
        result = task_manager.remove_account(mock_account_config.email)
        
        # Assert
        assert result
        assert mock_account_config.email not in task_manager.processors
    
    def test_remove_account_not_found(self, task_manager):
        """Test removing non-existent account"""
        # Act
        result = task_manager.remove_account("nonexistent@example.com")
        
        # Assert
        assert not result
    
    @patch('services.email_processor.EmailProcessor.start')
    def test_start_account_success(self, mock_start, task_manager, mock_account_config):
        """Test successfully starting an account"""
        # Arrange
        mock_start.return_value = True
        task_manager.add_account(mock_account_config)
        
        # Act
        result = task_manager.start_account(mock_account_config.email, ProcessingMode.STARTUP)
        
        # Assert
        assert result
        mock_start.assert_called_once_with(ProcessingMode.STARTUP)
    
    def test_start_account_not_found(self, task_manager):
        """Test starting non-existent account"""
        # Act
        result = task_manager.start_account("nonexistent@example.com")
        
        # Assert
        assert not result
    
    @patch('services.email_processor.EmailProcessor.stop')
    def test_stop_account_success(self, mock_stop, task_manager, mock_account_config):
        """Test successfully stopping an account"""
        # Arrange
        mock_stop.return_value = True
        task_manager.add_account(mock_account_config)
        
        # Act
        result = task_manager.stop_account(mock_account_config.email)
        
        # Assert
        assert result
        mock_stop.assert_called_once()
    
    @patch('services.email_processor.EmailProcessor.restart')
    def test_restart_account_success(self, mock_restart, task_manager, mock_account_config):
        """Test successfully restarting an account"""
        # Arrange
        mock_restart.return_value = True
        task_manager.add_account(mock_account_config)
        
        # Act
        result = task_manager.restart_account(mock_account_config.email)
        
        # Assert
        assert result
        mock_restart.assert_called_once()
    
    @patch('services.email_processor.EmailProcessor.switch_mode')
    def test_switch_mode_success(self, mock_switch_mode, task_manager, mock_account_config):
        """Test successfully switching mode"""
        # Arrange
        mock_switch_mode.return_value = True
        task_manager.add_account(mock_account_config)
        
        # Act
        result = task_manager.switch_mode(mock_account_config.email, ProcessingMode.MAINTENANCE)
        
        # Assert
        assert result
        mock_switch_mode.assert_called_once_with(ProcessingMode.MAINTENANCE)
    
    @patch('services.email_processor.EmailProcessor.get_status')
    def test_get_account_status(self, mock_get_status, task_manager, mock_account_config):
        """Test getting account status"""
        # Arrange
        expected_status = {'state': 'stopped', 'mode': 'startup'}
        mock_get_status.return_value = expected_status
        task_manager.add_account(mock_account_config)
        
        # Act
        result = task_manager.get_account_status(mock_account_config.email)
        
        # Assert
        assert result == expected_status
        mock_get_status.assert_called_once()
    
    def test_get_account_status_not_found(self, task_manager):
        """Test getting status for non-existent account"""
        # Act
        result = task_manager.get_account_status("nonexistent@example.com")
        
        # Assert
        assert result is None
    
    def test_get_all_status(self, task_manager, mock_account_config):
        """Test getting all status"""
        # Arrange
        task_manager.add_account(mock_account_config)
        
        # Act
        result = task_manager.get_all_status()
        
        # Assert
        assert 'task_manager' in result
        assert 'accounts' in result
        assert 'total_accounts' in result['task_manager']
        assert 'startup_time' in result['task_manager']
    
    def test_get_aggregate_stats(self, task_manager, mock_account_config):
        """Test getting aggregate statistics"""
        # Arrange
        task_manager.add_account(mock_account_config)
        
        # Act
        result = task_manager.get_aggregate_stats()
        
        # Assert
        assert 'total_accounts' in result
        assert 'running_accounts' in result
        assert 'total_emails_processed' in result
        assert 'total_emails_pending' in result
        assert 'error_rate' in result
    
    def test_get_task_history(self, task_manager, mock_account_config):
        """Test getting task history"""
        # Arrange
        task_manager.add_account(mock_account_config)
        
        # Act
        result = task_manager.get_task_history(limit=10)
        
        # Assert
        assert isinstance(result, list)
        assert len(result) <= 10
        if result:
            assert 'timestamp' in result[0]
            assert 'type' in result[0]


class TestSchedulerManager:
    """Test SchedulerManager class"""
    
    @pytest.fixture
    def scheduler_manager(self):
        """Create SchedulerManager instance for testing"""
        return SchedulerManager()
    
    @pytest.fixture
    def mock_scheduler(self):
        """Create mock scheduler"""
        scheduler = Mock()
        scheduler.running = True
        scheduler.get_jobs.return_value = []
        return scheduler
    
    def test_scheduler_manager_initialization(self, scheduler_manager):
        """Test SchedulerManager initialization"""
        # Assert
        assert len(scheduler_manager.registered_schedulers) == 0
        assert len(scheduler_manager.scheduler_info) == 0
    
    def test_register_scheduler(self, scheduler_manager, mock_scheduler):
        """Test registering a scheduler"""
        # Act
        scheduler_manager.register_scheduler("test_scheduler", mock_scheduler, "test@example.com")
        
        # Assert
        assert "test_scheduler" in scheduler_manager.registered_schedulers
        assert "test_scheduler" in scheduler_manager.scheduler_info
        
        info = scheduler_manager.scheduler_info["test_scheduler"]
        assert info.scheduler_id == "test_scheduler"
        assert info.account_email == "test@example.com"
    
    def test_unregister_scheduler(self, scheduler_manager, mock_scheduler):
        """Test unregistering a scheduler"""
        # Arrange
        scheduler_manager.register_scheduler("test_scheduler", mock_scheduler, "test@example.com")
        
        # Act
        scheduler_manager.unregister_scheduler("test_scheduler")
        
        # Assert
        assert "test_scheduler" not in scheduler_manager.registered_schedulers
        assert "test_scheduler" not in scheduler_manager.scheduler_info
    
    def test_get_scheduler_status_not_found(self, scheduler_manager):
        """Test getting status for non-existent scheduler"""
        # Act
        result = scheduler_manager.get_scheduler_status("nonexistent")
        
        # Assert
        assert result is None
    
    def test_get_scheduler_status_success(self, scheduler_manager, mock_scheduler):
        """Test getting scheduler status"""
        # Arrange
        scheduler_manager.register_scheduler("test_scheduler", mock_scheduler, "test@example.com")
        
        # Act
        result = scheduler_manager.get_scheduler_status("test_scheduler")
        
        # Assert
        assert result is not None
        assert result['scheduler_id'] == "test_scheduler"
        assert result['account_email'] == "test@example.com"
    
    def test_get_all_status(self, scheduler_manager, mock_scheduler):
        """Test getting all scheduler status"""
        # Arrange
        scheduler_manager.register_scheduler("test_scheduler", mock_scheduler, "test@example.com")
        
        # Act
        result = scheduler_manager.get_all_status()
        
        # Assert
        assert 'summary' in result
        assert 'schedulers' in result
        assert 'total_schedulers' in result['summary']
        assert 'running_schedulers' in result['summary']
    
    def test_get_jobs_summary(self, scheduler_manager, mock_scheduler):
        """Test getting jobs summary"""
        # Arrange
        mock_job = Mock()
        mock_job.id = "test_job"
        mock_job.name = "Test Job"
        mock_job.next_run_time = datetime.now()
        mock_job.trigger = "interval"
        mock_scheduler.get_jobs.return_value = [mock_job]
        
        scheduler_manager.register_scheduler("test_scheduler", mock_scheduler, "test@example.com")
        
        # Act
        result = scheduler_manager.get_jobs_summary()
        
        # Assert
        assert isinstance(result, list)
        if result:
            job_info = result[0]
            assert job_info['scheduler_id'] == "test_scheduler"
            assert job_info['job_id'] == "test_job"
            assert job_info['account_email'] == "test@example.com"


class TestGlobalInstances:
    """Test global instance functions"""
    
    def test_get_task_manager_singleton(self):
        """Test get_task_manager returns singleton"""
        # Act
        manager1 = get_task_manager()
        manager2 = get_task_manager()
        
        # Assert
        assert manager1 is manager2
        
        # Cleanup
        shutdown_task_manager()
    
    def test_shutdown_task_manager(self):
        """Test shutting down task manager"""
        # Arrange
        manager = get_task_manager()
        
        # Act
        shutdown_task_manager()
        
        # Assert
        # Getting task manager again should create new instance
        new_manager = get_task_manager()
        assert new_manager is not manager
        
        # Cleanup
        shutdown_task_manager()
    
    def test_get_scheduler_manager_singleton(self):
        """Test get_scheduler_manager returns singleton"""
        # Act
        manager1 = get_scheduler_manager()
        manager2 = get_scheduler_manager()
        
        # Assert
        assert manager1 is manager2