// Storage key for checklist progress. Kept as-is so returning visitors'
// saved checks survive this refactor.
const STORAGE_KEY = 'seoChecklistStates';

// Function to save checkbox states
function saveCheckboxStates() {
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    const states = {};

    checkboxes.forEach(checkbox => {
        states[checkbox.id] = checkbox.checked;
    });

    localStorage.setItem(STORAGE_KEY, JSON.stringify(states));
}

// Function to load checkbox states
function loadCheckboxStates() {
    const savedStates = localStorage.getItem(STORAGE_KEY);

    if (!savedStates) return;

    let states;
    try {
        states = JSON.parse(savedStates);
    } catch (err) {
        return;
    }

    const checkboxes = document.querySelectorAll('input[type="checkbox"]');

    checkboxes.forEach(checkbox => {
        if (Object.prototype.hasOwnProperty.call(states, checkbox.id)) {
            checkbox.checked = states[checkbox.id];
        }
    });
}

// Add a visual indicator that progress is saved
function addSaveIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'save-indicator';
    indicator.textContent = 'Progress saved ✓';
    document.body.appendChild(indicator);

    return indicator;
}

// Show save indicator
function showSaveIndicator(indicator) {
    indicator.classList.add('show');
    clearTimeout(showSaveIndicator._timer);
    showSaveIndicator._timer = setTimeout(() => {
        indicator.classList.remove('show');
    }, 2000);
}

// Build the sticky overall-progress bar (counter + bar + reset control)
function buildProgressCounter(container) {
    const progressDiv = document.createElement('div');
    progressDiv.className = 'progress-counter';
    progressDiv.innerHTML = `
        <div class="progress-counter-row">
            <span class="progress-counter-label" data-progress-text>0 of 0 done</span>
            <a class="progress-complete-cta" href="#pdf-download" hidden>All done. Get the PDF copy</a>
            <button type="button" class="progress-reset" data-progress-reset>Reset progress</button>
        </div>
        <div class="progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
            <div class="progress-fill" data-progress-fill></div>
        </div>
    `;
    container.prepend(progressDiv);
    return progressDiv;
}

// Give every section header a per-section count chip
function buildSectionCounters() {
    const sections = document.querySelectorAll('.section');
    const counters = [];

    sections.forEach(section => {
        const boxes = section.querySelectorAll('input[type="checkbox"]');
        if (!boxes.length) return;

        const header = section.querySelector('.section-header');
        if (!header) return;

        const chip = document.createElement('span');
        chip.className = 'section-progress';
        header.appendChild(chip);

        counters.push({ boxes, chip });
    });

    return counters;
}

// Initialize everything when the page loads
document.addEventListener('DOMContentLoaded', () => {
    const saveIndicator = addSaveIndicator();

    // Load saved states
    loadCheckboxStates();

    // Make entire checklist items clickable
    const checklistItems = document.querySelectorAll('.checklist-item');

    // Card + checkbox pairs, collected once so updateProgress can repaint the
    // checked-card state without a second change listener per checkbox.
    const itemPairs = [];

    checklistItems.forEach(item => {
        const itemCheckbox = item.querySelector('input[type="checkbox"]');
        if (!itemCheckbox) return;

        itemPairs.push({ item, checkbox: itemCheckbox });

        item.style.cursor = 'pointer'; // Add pointer cursor to indicate clickability

        item.addEventListener('click', (e) => {
            // Don't toggle if clicking on a link or label
            if (e.target.tagName === 'A' ||
                e.target.tagName === 'LABEL' ||
                e.target.closest('a') ||
                e.target.closest('label')) {
                return;
            }

            // Toggle the checkbox
            itemCheckbox.checked = !itemCheckbox.checked;

            // Trigger the change event manually
            itemCheckbox.dispatchEvent(new Event('change'));

            // Prevent text selection
            e.preventDefault();
        });

        // Prevent double-toggling when clicking the actual checkbox
        itemCheckbox.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        // Prevent text selection on the clickable area
        item.addEventListener('mousedown', (e) => {
            if (e.target.tagName !== 'A' &&
                !e.target.closest('a') &&
                e.target.tagName !== 'LABEL' &&
                !e.target.closest('label')) {
                e.preventDefault();
            }
        });
    });

    const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
    const totalCheckboxes = checkboxes.length;

    // Progress UI. Anchored to .section-container, which exists on the page
    // (the old code targeted a .intro element that never shipped, so this whole
    // feature threw a TypeError on every load).
    const sectionContainer = document.querySelector('.section-container');
    const sectionCounters = buildSectionCounters();
    const progressDiv = sectionContainer && totalCheckboxes
        ? buildProgressCounter(sectionContainer)
        : null;

    const progressText = progressDiv ? progressDiv.querySelector('[data-progress-text]') : null;
    const progressFill = progressDiv ? progressDiv.querySelector('[data-progress-fill]') : null;
    const progressTrack = progressDiv ? progressDiv.querySelector('.progress-track') : null;
    const completeCta = progressDiv ? progressDiv.querySelector('.progress-complete-cta') : null;

    function updateProgress() {
        const completed = checkboxes.filter(box => box.checked).length;
        const allDone = totalCheckboxes > 0 && completed === totalCheckboxes;

        // Checked-card state. Runs on load, on every change, and on reset.
        itemPairs.forEach(({ item, checkbox }) => {
            item.classList.toggle('is-done', checkbox.checked);
        });

        // Completion moment: the finished checklist offers the PDF.
        if (completeCta) completeCta.hidden = !allDone;

        if (progressText) {
            const percentage = totalCheckboxes
                ? Math.round((completed / totalCheckboxes) * 100)
                : 0;
            progressText.textContent = `${completed} of ${totalCheckboxes} done (${percentage}%)`;
            if (progressFill) progressFill.style.width = `${percentage}%`;
            if (progressTrack) progressTrack.setAttribute('aria-valuenow', String(percentage));
            if (progressDiv) progressDiv.classList.toggle('is-complete', allDone);
        }

        sectionCounters.forEach(({ boxes, chip }) => {
            const done = Array.from(boxes).filter(box => box.checked).length;
            chip.textContent = `${done}/${boxes.length}`;
            chip.classList.toggle('is-complete', done === boxes.length);
        });
    }

    // Single change handler: persist, toast, repaint progress
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', () => {
            saveCheckboxStates();
            showSaveIndicator(saveIndicator);
            updateProgress();
        });
    });

    // Reset control
    if (progressDiv) {
        const resetButton = progressDiv.querySelector('[data-progress-reset]');
        resetButton.addEventListener('click', () => {
            const anyChecked = checkboxes.some(box => box.checked);
            if (anyChecked && !window.confirm('Clear every check on this checklist?')) {
                return;
            }
            checkboxes.forEach(box => { box.checked = false; });
            localStorage.removeItem(STORAGE_KEY);
            updateProgress();
            showSaveIndicator(saveIndicator);
        });
    }

    updateProgress();

    // Neutral-until-touched form validation. The old CSS painted an empty
    // required email red on first focus; these flags let CSS wait until the
    // visitor has actually typed and left the field, or tried to submit.
    const captureForm = document.querySelector('.bento-formkit');
    if (captureForm) {
        const inputs = captureForm.querySelectorAll('input[type="email"], input[type="text"]');
        inputs.forEach(input => {
            input.addEventListener('blur', () => {
                if (input.value.trim() !== '') {
                    input.setAttribute('data-touched', '');
                } else {
                    input.removeAttribute('data-touched');
                }
            });
            input.addEventListener('input', () => {
                if (input.value.trim() === '') {
                    input.removeAttribute('data-touched');
                }
            });
        });
        captureForm.addEventListener('submit', () => {
            inputs.forEach(input => input.setAttribute('data-touched', ''));
        });
    }

    // Mobile sticky capture bar. Dismissible; the dismissal sticks per browser.
    const stickyBar = document.querySelector('.sticky-capture');
    if (stickyBar) {
        if (localStorage.getItem('seoChecklistStickyDismissed') === 'true') {
            stickyBar.remove();
        } else {
            stickyBar.hidden = false;
            const dismiss = stickyBar.querySelector('[data-sticky-dismiss]');
            if (dismiss) {
                dismiss.addEventListener('click', () => {
                    localStorage.setItem('seoChecklistStickyDismissed', 'true');
                    stickyBar.remove();
                });
            }
            const cta = stickyBar.querySelector('[data-sticky-cta]');
            if (cta) {
                cta.addEventListener('click', (e) => {
                    const target = document.getElementById('pdf-download');
                    if (target) {
                        e.preventDefault();
                        target.scrollIntoView({ behavior: 'smooth' });
                    }
                });
            }
        }
    }
});
