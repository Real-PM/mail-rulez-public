/*
 * Mail-Rulez - Intelligent Email Management System
 * Copyright (c) 2024 Real Project Management Solutions
 * Dual-licensed software. See LICENSE-DUAL for details.
 */


// Mail-Rulez Web Interface JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        if (!alert.classList.contains('alert-danger')) {
            setTimeout(function() {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }, 5000);
        }
    });

    // Add loading state to forms
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function() {
            const submitBtn = form.querySelector('input[type="submit"], button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                const originalText = submitBtn.textContent;
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> ' + originalText;
            }
        });
    });

    // Session timeout warning
    checkSessionStatus();
    setInterval(checkSessionStatus, 60000); // Check every minute
});

// Session management
function checkSessionStatus() {
    // Don't check session status on auth pages (login, setup)
    if (window.location.pathname.startsWith('/auth/')) {
        return;
    }
    
    fetch('/auth/session/status')
        .then(response => response.json())
        .then(data => {
            if (!data.authenticated) {
                showSessionExpiredModal();
            }
        })
        .catch(error => {
            console.log('Session check failed:', error);
        });
}

function showSessionExpiredModal() {
    // Create a simple modal for session expiration
    const modal = document.createElement('div');
    modal.innerHTML = `
        <div class="modal fade" id="sessionExpiredModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Session Expired</h5>
                    </div>
                    <div class="modal-body">
                        Your session has expired. Please log in again.
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-primary" onclick="window.location.href='/auth/login'">
                            Login Again
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    const sessionModal = new bootstrap.Modal(document.getElementById('sessionExpiredModal'));
    sessionModal.show();
}

// Utility functions
function showLoading(element) {
    element.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Loading...';
    element.disabled = true;
}

function hideLoading(element, originalText) {
    element.innerHTML = originalText;
    element.disabled = false;
}

// CSRF token handling for AJAX requests
function getCSRFToken() {
    return document.querySelector('meta[name=csrf-token]')?.getAttribute('content');
}

// Setup AJAX requests with CSRF token
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
    if (options.method && options.method.toUpperCase() !== 'GET') {
        options.headers = options.headers || {};
        options.headers['X-CSRFToken'] = getCSRFToken();
    }
    return originalFetch(url, options);
};