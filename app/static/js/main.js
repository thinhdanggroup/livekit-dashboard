// LiveKit Dashboard Client-Side JavaScript

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('LiveKit Dashboard initialized');
    
    // Fix text colors for dark theme
    fixTextColors();
    
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});

/**
 * Fix text color issues in dark theme
 */
function fixTextColors() {
    // Find all elements with black or dark text
    const allElements = document.querySelectorAll('*');
    
    allElements.forEach(element => {
        const computedStyle = window.getComputedStyle(element);
        const color = computedStyle.color;
        
        // Check if text is black or very dark
        if (color === 'rgb(0, 0, 0)' || color === '#000000' || color === 'black' ||
            color === 'rgb(33, 37, 41)' || color === '#212529') {
            
            // Apply proper text color based on element type
            if (element.closest('.alert-success')) {
                element.style.color = 'var(--success)';
            } else if (element.closest('.alert-danger, .alert-error')) {
                element.style.color = 'var(--danger)';
            } else if (element.closest('.alert-warning')) {
                element.style.color = 'var(--warning)';
            } else if (element.closest('.alert-info')) {
                element.style.color = 'var(--info)';
            } else if (element.closest('.text-muted')) {
                element.style.color = 'var(--text-muted)';
            } else {
                element.style.color = 'var(--text-primary)';
            }
        }
    });
    
    // Fix specific recommendation/failure message elements
    const messageBoxes = document.querySelectorAll('.recommendation-box, .message-box, .failure-message, .error-message');
    messageBoxes.forEach(box => {
        box.style.color = 'var(--text-primary)';
        const allChildren = box.querySelectorAll('*');
        allChildren.forEach(child => {
            if (!child.style.color || child.style.color === 'black' || child.style.color === 'rgb(0, 0, 0)') {
                child.style.color = 'inherit';
            }
        });
    });
}

// HTMX event handlers
document.body.addEventListener('htmx:beforeRequest', function(event) {
    console.log('HTMX request starting:', event.detail.path);
});

document.body.addEventListener('htmx:afterRequest', function(event) {
    console.log('HTMX request completed:', event.detail.path);
});

document.body.addEventListener('htmx:responseError', function(event) {
    console.error('HTMX error:', event.detail);
    showNotification('Error loading data. Please refresh the page.', 'danger');
});

// Utility Functions

/**
 * Show a temporary notification
 */
function showNotification(message, type = 'info') {
    const container = document.querySelector('.container-fluid') || document.querySelector('.container');
    if (!container) return;
    
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    container.insertBefore(alertDiv, container.firstChild);
    
    setTimeout(() => {
        const bsAlert = new bootstrap.Alert(alertDiv);
        bsAlert.close();
    }, 5000);
}

/**
 * Copy text to clipboard
 */
function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(() => {
                showNotification('Copied to clipboard!', 'success');
            })
            .catch(err => {
                console.error('Failed to copy:', err);
                fallbackCopyToClipboard(text);
            });
    } else {
        fallbackCopyToClipboard(text);
    }
}

/**
 * Fallback copy method for older browsers
 */
function fallbackCopyToClipboard(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.top = '0';
    textArea.style.left = '0';
    textArea.style.opacity = '0';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    
    try {
        const successful = document.execCommand('copy');
        if (successful) {
            showNotification('Copied to clipboard!', 'success');
        } else {
            showNotification('Failed to copy to clipboard', 'danger');
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
        showNotification('Failed to copy to clipboard', 'danger');
    }
    
    document.body.removeChild(textArea);
}

/**
 * Format duration in seconds to human readable
 */
function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    const parts = [];
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0) parts.push(`${minutes}m`);
    if (secs > 0 || parts.length === 0) parts.push(`${secs}s`);
    
    return parts.join(' ');
}

/**
 * Format timestamp to relative time
 */
function formatRelativeTime(timestamp) {
    const now = Date.now();
    const diff = now - timestamp;
    const seconds = Math.floor(diff / 1000);
    
    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
    return `${Math.floor(seconds / 86400)} days ago`;
}

/**
 * Confirm action with custom message
 */
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

/**
 * Handle form submission with loading state
 */
function handleFormSubmit(formElement, onSuccess) {
    const submitBtn = formElement.querySelector('[type="submit"]');
    const originalText = submitBtn.innerHTML;
    
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
    
    const formData = new FormData(formElement);
    
    fetch(formElement.action, {
        method: formElement.method || 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) throw new Error('Request failed');
        return response.json();
    })
    .then(data => {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
        if (onSuccess) onSuccess(data);
    })
    .catch(error => {
        console.error('Form submission error:', error);
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
        showNotification('An error occurred. Please try again.', 'danger');
    });
}

// Export functions for use in templates
window.dashboardUtils = {
    showNotification,
    copyToClipboard,
    formatDuration,
    formatRelativeTime,
    confirmAction,
    handleFormSubmit,
    fixTextColors
};

