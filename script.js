// Function to save checkbox states
function saveCheckboxStates() {
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    const states = {};
    
    checkboxes.forEach(checkbox => {
        states[checkbox.id] = checkbox.checked;
    });
    
    localStorage.setItem('seoChecklistStates', JSON.stringify(states));
}

// Function to load checkbox states
function loadCheckboxStates() {
    const savedStates = localStorage.getItem('seoChecklistStates');
    
    if (savedStates) {
        const states = JSON.parse(savedStates);
        const checkboxes = document.querySelectorAll('input[type="checkbox"]');
        
        checkboxes.forEach(checkbox => {
            if (states.hasOwnProperty(checkbox.id)) {
                checkbox.checked = states[checkbox.id];
            }
        });
    }
}

// Add event listeners to all checkboxes
function initializeCheckboxes() {
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', saveCheckboxStates);
    });
}

// Add a visual indicator that progress is saved
function addSaveIndicator() {
    const style = document.createElement('style');
    style.textContent = `
        .save-indicator {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #008060;
            color: white;
            padding: 8px 16px;
            border-radius: 4px;
            font-size: 0.9em;
            opacity: 0;
            transition: opacity 0.3s ease;
            pointer-events: none;
        }
        .save-indicator.show {
            opacity: 1;
        }
    `;
    document.head.appendChild(style);

    const indicator = document.createElement('div');
    indicator.className = 'save-indicator';
    indicator.textContent = 'Progress saved ✓';
    document.body.appendChild(indicator);

    return indicator;
}

// Show save indicator
function showSaveIndicator(indicator) {
    indicator.classList.add('show');
    setTimeout(() => {
        indicator.classList.remove('show');
    }, 2000);
}

// Initialize everything when the page loads
document.addEventListener('DOMContentLoaded', () => {
    const saveIndicator = addSaveIndicator();
    
    // Load saved states
    loadCheckboxStates();
    
    // Initialize checkbox event listeners
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', () => {
            saveCheckboxStates();
            showSaveIndicator(saveIndicator);
        });
    });

    // Add progress counter
    const totalCheckboxes = checkboxes.length;
    const checkedCount = () => document.querySelectorAll('input[type="checkbox"]:checked').length;
    
    const progressDiv = document.createElement('div');
    progressDiv.className = 'progress-counter';
    progressDiv.style.cssText = `
        position: sticky;
        top: 20px;
        background: white;
        padding: 10px 20px;
        border-radius: 4px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 20px;
        z-index: 100;
        text-align: center;
        border-left: 4px solid #008060;
    `;
    
    function updateProgress() {
        const completed = checkedCount();
        const percentage = Math.round((completed / totalCheckboxes) * 100);
        progressDiv.innerHTML = `
            <strong>Progress: ${completed}/${totalCheckboxes} (${percentage}%)</strong>
        `;
    }

    document.querySelector('.intro').after(progressDiv);
    updateProgress();

    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', updateProgress);
    });

    // Save checkbox states to localStorage
    document.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
        // Load saved state
        const savedState = localStorage.getItem(checkbox.id);
        if (savedState === 'true') {
            checkbox.checked = true;
        }
        
        // Save state on change
        checkbox.addEventListener('change', (e) => {
            localStorage.setItem(e.target.id, e.target.checked);
        });
    });
}); 