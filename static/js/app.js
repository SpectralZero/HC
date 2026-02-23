/**
 * CareBox Client-Side JavaScript
 * 
 * Handles:
 * - Language detection and persistence
 * - Form validation enhancements
 * - UI micro-interactions
 */

(function() {
    'use strict';

    // =============================================================================
    // UTILITIES
    // =============================================================================

    /**
     * Get a cookie value by name
     */
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }

    /**
     * Debounce function for performance
     */
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // =============================================================================
    // FORM VALIDATION
    // =============================================================================

    /**
     * Enhance form validation with real-time feedback
     */
    function initFormValidation() {
        const forms = document.querySelectorAll('form.order-form');
        
        forms.forEach(form => {
            const inputs = form.querySelectorAll('input[required], textarea[required]');
            
            inputs.forEach(input => {
                // Add validation on blur
                input.addEventListener('blur', function() {
                    validateInput(this);
                });
                
                // Clear error on input
                input.addEventListener('input', debounce(function() {
                    if (this.classList.contains('is-invalid')) {
                        validateInput(this);
                    }
                }, 300));
            });
            
            // Prevent submission if invalid
            form.addEventListener('submit', function(e) {
                let isValid = true;
                
                // Validate all required inputs
                inputs.forEach(input => {
                    if (!validateInput(input)) {
                        isValid = false;
                    }
                });
                
                // Check radio buttons (box type)
                const boxTypeInputs = form.querySelectorAll('input[name="box_type"]');
                if (boxTypeInputs.length > 0) {
                    const isBoxTypeSelected = Array.from(boxTypeInputs).some(input => input.checked);
                    if (!isBoxTypeSelected) {
                        isValid = false;
                        highlightBoxTypeError(true);
                    }
                }
                
                if (!isValid) {
                    e.preventDefault();
                    // Scroll to first error
                    const firstError = form.querySelector('.is-invalid');
                    if (firstError) {
                        firstError.focus();
                        firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }
            });
        });
    }

    /**
     * Validate a single input
     */
    function validateInput(input) {
        const value = input.value.trim();
        let isValid = true;
        let errorMessage = '';
        
        // Check required
        if (input.hasAttribute('required') && !value) {
            isValid = false;
            errorMessage = 'This field is required';
        }
        
        // Check pattern (phone)
        if (isValid && input.type === 'tel' && input.pattern) {
            const pattern = new RegExp(input.pattern);
            if (!pattern.test(value)) {
                isValid = false;
                errorMessage = 'Please enter a valid phone number';
            }
        }
        
        // Check maxlength
        if (isValid && input.maxLength > 0 && value.length > input.maxLength) {
            isValid = false;
            errorMessage = `Maximum ${input.maxLength} characters allowed`;
        }
        
        // Update UI
        if (isValid) {
            input.classList.remove('is-invalid');
            input.classList.add('is-valid');
            removeErrorMessage(input);
        } else {
            input.classList.remove('is-valid');
            input.classList.add('is-invalid');
            showErrorMessage(input, errorMessage);
        }
        
        return isValid;
    }

    /**
     * Show error message below input
     */
    function showErrorMessage(input, message) {
        removeErrorMessage(input);
        
        const errorDiv = document.createElement('div');
        errorDiv.className = 'invalid-feedback d-block';
        errorDiv.textContent = message;
        errorDiv.style.color = '#dc3545';
        errorDiv.style.fontSize = '0.875rem';
        errorDiv.style.marginTop = '0.25rem';
        
        input.parentNode.appendChild(errorDiv);
    }

    /**
     * Remove error message
     */
    function removeErrorMessage(input) {
        const existingError = input.parentNode.querySelector('.invalid-feedback');
        if (existingError) {
            existingError.remove();
        }
    }

    /**
     * Highlight box type selection error
     */
    function highlightBoxTypeError(show) {
        const boxTypeGrid = document.querySelector('.box-type-grid');
        if (boxTypeGrid) {
            if (show) {
                boxTypeGrid.style.outline = '2px solid #dc3545';
                boxTypeGrid.style.outlineOffset = '4px';
                boxTypeGrid.style.borderRadius = '8px';
            } else {
                boxTypeGrid.style.outline = '';
                boxTypeGrid.style.outlineOffset = '';
            }
        }
    }

    // =============================================================================
    // BOX TYPE SELECTION
    // =============================================================================

    /**
     * Initialize box type selection interactions
     */
    function initBoxTypeSelection() {
        const boxTypeInputs = document.querySelectorAll('input[name="box_type"]');
        
        boxTypeInputs.forEach(input => {
            input.addEventListener('change', function() {
                // Clear any error highlighting
                highlightBoxTypeError(false);
                
                // Add selected animation
                const card = this.nextElementSibling;
                if (card) {
                    card.style.transform = 'scale(1.02)';
                    setTimeout(() => {
                        card.style.transform = '';
                    }, 150);
                }
            });
        });
    }

    // =============================================================================
    // SMOOTH SCROLL
    // =============================================================================

    /**
     * Initialize smooth scrolling for anchor links
     */
    function initSmoothScroll() {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function(e) {
                const href = this.getAttribute('href');
                if (href === '#') return;
                
                const target = document.querySelector(href);
                if (target) {
                    e.preventDefault();
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });
    }

    // =============================================================================
    // ALERT AUTO-DISMISS
    // =============================================================================

    /**
     * Auto-dismiss alerts after delay
     */
    function initAlertDismiss() {
        const alerts = document.querySelectorAll('.alert:not(.alert-danger)');
        
        alerts.forEach(alert => {
            setTimeout(() => {
                const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                bsAlert.close();
            }, 5000);
        });
    }

    // =============================================================================
    // INITIALIZATION
    // =============================================================================

    /**
     * Initialize all features on DOM ready
     */
    function init() {
        initFormValidation();
        initBoxTypeSelection();
        initSmoothScroll();
        initAlertDismiss();
        
        console.log('CareBox initialized');
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
