/* ═══════════════════════════════════════════════════════════════════════
   AI DOCTOR — VIRTUAL MEDICAL ASSISTANT
   Frontend JavaScript — Luminous-UI Replica (Vanilla ES6)

   Modules:
   1. Theme System
   2. Particle Generator
   3. Navbar Controller
   4. Scroll Animations (IntersectionObserver)
   5. Smooth Scroll
   6. Chat State Machine
   7. Patient Form Handler
   8. File Upload Zones
   9. Message Renderer
   10. Follow-up Question Flow
   11. Prescription Generator & Modal
   12. Chat Input Controller
   13. Initialization
   ═══════════════════════════════════════════════════════════════════════ */

'use strict';

/* ═══════════════════════════════════════════════════════════════════════
   1. THEME SYSTEM
   ═══════════════════════════════════════════════════════════════════════ */

const Theme = (() => {
    const STORAGE_KEY = 'luminous-theme';

    function get() {
        return localStorage.getItem(STORAGE_KEY) || 'dark';
    }

    function apply(theme) {
        document.documentElement.classList.toggle('light', theme === 'light');
        localStorage.setItem(STORAGE_KEY, theme);
    }

    function toggle() {
        const next = get() === 'dark' ? 'light' : 'dark';
        apply(next);
    }

    function init() {
        apply(get());
        document.querySelectorAll('#theme-toggle').forEach(btn => {
            btn.addEventListener('click', toggle);
        });
    }

    return { init, toggle, get };
})();


/* ═══════════════════════════════════════════════════════════════════════
   2. PARTICLE GENERATOR
   ═══════════════════════════════════════════════════════════════════════ */

const Particles = (() => {
    function generate(containerId, count = 30) {
        const container = document.getElementById(containerId);
        if (!container) return;

        for (let i = 0; i < count; i++) {
            const particle = document.createElement('div');
            particle.className = 'particle';
            const size = Math.random() * 3 + 1;
            const duration = Math.random() * 15 + 10;
            const delay = Math.random() * -20;
            const left = Math.random() * 100;

            particle.style.cssText = `
                width: ${size}px;
                height: ${size}px;
                left: ${left}%;
                bottom: -10px;
                animation-duration: ${duration}s;
                animation-delay: ${delay}s;
                opacity: ${Math.random() * 0.5 + 0.2};
            `;
            container.appendChild(particle);
        }
    }

    return { generate };
})();


/* ═══════════════════════════════════════════════════════════════════════
   3. NAVBAR CONTROLLER
   ═══════════════════════════════════════════════════════════════════════ */

const Navbar = (() => {
    function init() {
        const navbar = document.getElementById('navbar');
        const mobileToggle = document.getElementById('mobile-toggle');
        const mobileOverlay = document.getElementById('mobile-overlay');

        if (!navbar) return;

        // Scroll class
        const updateScroll = () => {
            navbar.classList.toggle('scrolled', window.scrollY > 20);
        };
        window.addEventListener('scroll', updateScroll, { passive: true });
        updateScroll();

        // Mobile menu
        if (mobileToggle && mobileOverlay) {
            mobileToggle.addEventListener('click', () => {
                const isOpen = mobileOverlay.classList.toggle('open');
                mobileToggle.classList.toggle('active', isOpen);
                mobileToggle.setAttribute('aria-expanded', String(isOpen));
                mobileOverlay.setAttribute('aria-hidden', String(!isOpen));
                document.body.style.overflow = isOpen ? 'hidden' : '';
            });

            // Close on link click
            mobileOverlay.querySelectorAll('a').forEach(link => {
                link.addEventListener('click', () => {
                    mobileOverlay.classList.remove('open');
                    mobileToggle.classList.remove('active');
                    mobileToggle.setAttribute('aria-expanded', 'false');
                    mobileOverlay.setAttribute('aria-hidden', 'true');
                    document.body.style.overflow = '';
                });
            });
        }
    }

    return { init };
})();


/* ═══════════════════════════════════════════════════════════════════════
   4. SCROLL ANIMATIONS (IntersectionObserver)
   ═══════════════════════════════════════════════════════════════════════ */

const ScrollAnimator = (() => {
    function init() {
        const targets = document.querySelectorAll(
            '.feature-card, .step, .tech-card, .cta__card'
        );
        if (!targets.length) return;

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.15, rootMargin: '0px 0px -50px 0px' });

        targets.forEach(el => observer.observe(el));
    }

    return { init };
})();


/* ═══════════════════════════════════════════════════════════════════════
   5. SMOOTH SCROLL
   ═══════════════════════════════════════════════════════════════════════ */

const SmoothScroll = (() => {
    function init() {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', e => {
                const id = anchor.getAttribute('href');
                if (!id || id === '#') return;
                const target = document.querySelector(id);
                if (!target) return;
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        });
    }

    return { init };
})();


/* ═══════════════════════════════════════════════════════════════════════
   6. CHAT STATE MACHINE
   ═══════════════════════════════════════════════════════════════════════ */

const FOLLOW_UP_QUESTIONS = [
    "On a scale of 1 to 10, how would you rate the severity of your symptoms?",
    "When did you first start experiencing these symptoms?",
    "Have you experienced similar symptoms before in the past?",
    "Are you currently taking any medications, vitamins, or supplements?",
    "Do you have any known allergies, especially to medications?",
    "Do you have any pre-existing medical conditions?",
    "Have you noticed any other symptoms accompanying your main complaint?",
    "Is there any family history of relevant medical conditions?",
];

const ChatState = (() => {
    let state = {
        phase: 'idle',       // idle | symptom | followup | complete
        patient: null,       // { name, age, gender }
        messages: [],        // [{ role, content, time }]
        questionIdx: 0,
        answers: [],
        xrayFile: null,
        reportFile: null,
        prescription: null,
        isProcessing: false,
    };

    function get() { return state; }

    function set(updates) {
        Object.assign(state, updates);
    }

    function reset() {
        state = {
            phase: 'idle',
            patient: null,
            messages: [],
            questionIdx: 0,
            answers: [],
            xrayFile: null,
            reportFile: null,
            prescription: null,
            isProcessing: false,
        };
    }

    return { get, set, reset };
})();


/* ═══════════════════════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════════════════════ */

function getTimeStamp() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatContent(text) {
    let html = escapeHtml(text);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\n/g, '<br/>');
    return html;
}


/* ═══════════════════════════════════════════════════════════════════════
   9. MESSAGE RENDERER
   ═══════════════════════════════════════════════════════════════════════ */

const MessageRenderer = (() => {
    function render(container) {
        if (!container) return;
        const { messages, phase, prescription, isProcessing } = ChatState.get();
        container.innerHTML = '';

        messages.forEach(msg => {
            if (msg.role === 'system') {
                container.appendChild(createSystemMsg(msg.content));
            } else {
                container.appendChild(createChatMsg(msg));
            }
        });

        // View Prescription button
        if (phase === 'complete' && prescription) {
            container.appendChild(createRxButton());
        }

        // Typing indicator
        if (isProcessing) {
            container.appendChild(createTypingIndicator());
        }

        scrollToBottom(container.parentElement);
    }

    function createSystemMsg(content) {
        const div = document.createElement('div');
        div.className = 'chat-system-msg';
        div.innerHTML = `<span class="chat-system-msg__pill">${escapeHtml(content)}</span>`;
        return div;
    }

    function createChatMsg(msg) {
        const isAi = msg.role === 'ai';
        const wrapper = document.createElement('div');
        wrapper.className = `chat-msg chat-msg--${msg.role}`;

        const avatar = document.createElement('div');
        avatar.className = 'chat-msg__avatar';
        avatar.textContent = isAi ? '🩺' : '👤';

        const body = document.createElement('div');
        body.className = 'chat-msg__body';

        const bubble = document.createElement('div');
        bubble.className = 'chat-msg__bubble';
        bubble.innerHTML = formatContent(msg.content);

        const time = document.createElement('span');
        time.className = 'chat-msg__time';
        time.textContent = msg.time;

        body.appendChild(bubble);
        body.appendChild(time);

        wrapper.appendChild(avatar);
        wrapper.appendChild(body);
        return wrapper;
    }

    function createRxButton() {
        const wrapper = document.createElement('div');
        wrapper.className = 'chat-msg chat-msg--ai';

        const avatar = document.createElement('div');
        avatar.className = 'chat-msg__avatar';
        avatar.textContent = '🩺';

        const body = document.createElement('div');
        body.className = 'chat-msg__rx-btn';

        const btn = document.createElement('button');
        btn.textContent = '📋 View Prescription';
        btn.addEventListener('click', PrescriptionModal.open);

        body.appendChild(btn);
        wrapper.appendChild(avatar);
        wrapper.appendChild(body);
        return wrapper;
    }

    function createTypingIndicator() {
        const div = document.createElement('div');
        div.className = 'typing-indicator';
        div.innerHTML = `
            <div class="typing-indicator__avatar">🩺</div>
            <div class="typing-indicator__dots">
                <span></span><span></span><span></span>
            </div>
        `;
        return div;
    }

    function scrollToBottom(scrollable) {
        if (!scrollable) return;
        requestAnimationFrame(() => {
            scrollable.scrollTop = scrollable.scrollHeight;
        });
    }

    return { render, scrollToBottom };
})();


/* ═══════════════════════════════════════════════════════════════════════
   7. PATIENT FORM HANDLER
   ═══════════════════════════════════════════════════════════════════════ */

const PatientForm = (() => {
    function init() {
        const overlay = document.getElementById('form-overlay');
        const form = document.getElementById('patient-form');
        if (!overlay || !form) return;

        form.addEventListener('submit', handleSubmit);

        // Age arrow functionality
        const ageInput = document.getElementById('patient-age');
        const upArrow = document.querySelector('.age-arrow--up');
        const downArrow = document.querySelector('.age-arrow--down');

        if (upArrow && downArrow && ageInput) {
            upArrow.addEventListener('click', () => adjustAge(ageInput, 1));
            downArrow.addEventListener('click', () => adjustAge(ageInput, -1));
        }
    }

    function adjustAge(input, delta) {
        let value = parseInt(input.value) || 0;
        value += delta;
        value = Math.max(1, Math.min(120, value)); // Clamp between 1 and 120
        input.value = value;
    }

    function handleSubmit(e) {
        e.preventDefault();
        const name = document.getElementById('patient-name').value.trim();
        const age = document.getElementById('patient-age').value.trim();
        const gender = document.getElementById('patient-gender').value;

        if (!name || !age || !gender) return;

        const { xrayFile, reportFile } = ChatState.get();

        ChatState.set({
            patient: { name, age, gender },
            phase: 'symptom',
        });

        // Hide form with animation
        const overlay = document.getElementById('form-overlay');
        overlay.classList.add('form-overlay--hiding');
        setTimeout(() => {
            overlay.classList.add('hidden');
            overlay.classList.remove('form-overlay--hiding');
        }, 300);

        // Update header status
        updateHeaderStatus('Consultation active');

        // Welcome message
        let welcome = `Hello, ${name}! I'm your AI Doctor. 👋\n\nI can see you're ${age} years old. Welcome to your virtual medical consultation.\n\n`;
        if (xrayFile) welcome += '📸 I received your X-ray image — I\'ll analyze it as part of the consultation.\n';
        if (reportFile) welcome += '📋 I received your medical test report — I\'ll include its findings.\n';
        welcome += '\nPlease describe your symptoms in detail so I can begin the assessment.';

        setTimeout(() => {
            addMessage('ai', welcome);
            addMessage('system', 'Consultation started — describe your symptoms below');
            rerenderChat();
            enableInput();
        }, 400);
    }

    return { init };
})();


/* ═══════════════════════════════════════════════════════════════════════
   8. FILE UPLOAD ZONES
   ═══════════════════════════════════════════════════════════════════════ */

const FileUpload = (() => {
    function init() {
        setup('xray-upload', 'xray-file', 'xrayFile');
        setup('lab-upload', 'lab-file', 'reportFile');
    }

    function setup(zoneId, inputId, stateKey) {
        const zone = document.getElementById(zoneId);
        const input = document.getElementById(inputId);
        if (!zone || !input) return;

        // Click to open
        zone.addEventListener('click', (e) => {
            if (e.target.closest('.file-upload__remove')) return;
            if (!zone.classList.contains('has-file')) {
                input.click();
            }
        });

        // Keyboard
        zone.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                if (!zone.classList.contains('has-file')) {
                    input.click();
                }
            }
        });

        // File selected
        input.addEventListener('change', () => {
            if (input.files && input.files[0]) {
                setFile(zone, input.files[0], stateKey);
            }
        });

        // Drag & drop
        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            zone.classList.add('dragover');
        });

        zone.addEventListener('dragleave', () => {
            zone.classList.remove('dragover');
        });

        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('dragover');
            if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                setFile(zone, e.dataTransfer.files[0], stateKey);
            }
        });

        // Remove button
        const removeBtn = zone.querySelector('.file-upload__remove');
        if (removeBtn) {
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                clearFile(zone, input, stateKey);
            });
        }
    }

    function setFile(zone, file, stateKey) {
        ChatState.set({ [stateKey]: file });
        zone.classList.add('has-file');
        const nameEl = zone.querySelector('.file-upload__filename');
        if (nameEl) nameEl.textContent = file.name;
    }

    function clearFile(zone, input, stateKey) {
        ChatState.set({ [stateKey]: null });
        zone.classList.remove('has-file');
        input.value = '';
        const nameEl = zone.querySelector('.file-upload__filename');
        if (nameEl) nameEl.textContent = '';
    }

    return { init };
})();


/* ═══════════════════════════════════════════════════════════════════════
   10. FOLLOW-UP QUESTION FLOW
   ═══════════════════════════════════════════════════════════════════════ */

async function processSymptoms(symptomText) {
    ChatState.set({ isProcessing: true });
    updateHeaderStatus('AI Doctor is thinking...');
    rerenderChat();

    await wait(2000 + Math.random() * 1500);

    ChatState.set({ isProcessing: false });
    updateHeaderStatus('Consultation active');

    const { xrayFile, reportFile } = ChatState.get();

    if (xrayFile) {
        addMessage('ai', '🩻 **X-Ray Analysis:** I\'ve processed your uploaded X-ray image. The AI fracture detection model has analyzed the image, and I\'ll incorporate the findings into the diagnosis.\n\nNow, I need to ask you some follow-up questions to better understand your condition.');
        rerenderChat();
        await wait(1000);
    }

    if (reportFile) {
        addMessage('ai', '📋 **Test Report Received:** Your medical test report has been processed via OCR, and the extracted data will be considered in the assessment.');
        rerenderChat();
        await wait(1000);
    }

    ChatState.set({
        phase: 'followup',
        questionIdx: 0,
        answers: [],
    });

    addMessage('ai', `**Question 1 of ${FOLLOW_UP_QUESTIONS.length}:**\n\n${FOLLOW_UP_QUESTIONS[0]}`);
    rerenderChat();
}

async function processFollowUp(answerText) {
    const s = ChatState.get();
    const newAnswers = [...s.answers, answerText];
    const nextIdx = s.questionIdx + 1;

    ChatState.set({ answers: newAnswers });

    if (nextIdx < FOLLOW_UP_QUESTIONS.length) {
        ChatState.set({ isProcessing: true });
        updateHeaderStatus('AI Doctor is thinking...');
        rerenderChat();

        await wait(800 + Math.random() * 800);

        ChatState.set({
            isProcessing: false,
            questionIdx: nextIdx,
        });
        updateHeaderStatus('Consultation active');

        addMessage('ai', `**Question ${nextIdx + 1} of ${FOLLOW_UP_QUESTIONS.length}:**\n\n${FOLLOW_UP_QUESTIONS[nextIdx]}`);
        rerenderChat();
    } else {
        addMessage('system', 'All follow-up questions answered ✅');
        rerenderChat();
        await generatePrescription();
    }
}


/* ═══════════════════════════════════════════════════════════════════════
   11. PRESCRIPTION GENERATOR & MODAL
   ═══════════════════════════════════════════════════════════════════════ */

async function generatePrescription() {
    ChatState.set({ isProcessing: true });
    updateHeaderStatus('Generating prescription...');
    rerenderChat();

    await wait(3000 + Math.random() * 2000);

    const { patient, xrayFile, reportFile } = ChatState.get();
    const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });

    const rx = {
        patient_info: {
            name: patient.name,
            age: parseInt(patient.age),
            gender: patient.gender,
            date: today,
        },
        diagnosis: 'This is a simulated diagnosis. When connected to the backend, the AI will provide a detailed clinical diagnosis based on your symptoms, follow-up answers, and any uploaded medical files.',
        medication: [
            {
                name: 'Simulated Medication A',
                dosage_and_route: '500mg orally',
                frequency_and_duration: 'Twice daily for 7 days',
                refills: 'None',
                special_instructions: 'Take with food.',
            },
            {
                name: 'Simulated Medication B',
                dosage_and_route: '10mg orally',
                frequency_and_duration: 'Once daily for 14 days',
                refills: '1 refill',
                special_instructions: 'Take before bedtime.',
            },
        ],
        non_pharmacological_recommendations: [
            { title: 'Ensure adequate rest and hydration' },
            { title: 'Monitor symptoms and seek emergency care if they worsen' },
            { title: 'Schedule a follow-up appointment in 2 weeks' },
        ],
        medical_tests: [
            { test_name: 'Complete Blood Count (CBC)' },
            { test_name: 'Basic Metabolic Panel' },
        ],
        prescriber: { name: 'AI Doctor — Virtual Medical Assistant' },
    };

    ChatState.set({
        prescription: rx,
        phase: 'complete',
        isProcessing: false,
    });
    updateHeaderStatus('Consultation complete');

    const fileNote = (xrayFile ? ', the X-ray findings' : '') + (reportFile ? ', and your medical test results' : '');
    addMessage('ai', `Based on my analysis of your symptoms, your answers to the follow-up questions${fileNote}, I've prepared a comprehensive medical prescription for you.\n\n**Diagnosis:** ${rx.diagnosis}\n\nPlease review the full prescription below. Remember, this is an AI-generated assessment — always consult a qualified healthcare provider for confirmation.`);
    addMessage('ai', '📋 **Your prescription is ready!**\n\nYou can view the complete prescription with medications, recommendations, and tests by clicking the button below.');
    addMessage('system', 'Consultation complete — You can start a new one anytime');

    rerenderChat();
    disableInput();
}

const PrescriptionModal = (() => {
    function open() {
        const modal = document.getElementById('rx-modal');
        const body = document.getElementById('rx-body');
        const { prescription } = ChatState.get();
        if (!modal || !body || !prescription) return;

        body.innerHTML = buildPrescriptionHTML(prescription);
        modal.classList.remove('hidden');
        modal.classList.remove('modal-overlay--closing');

        // Trap focus
        document.body.style.overflow = 'hidden';
    }

    function close() {
        const modal = document.getElementById('rx-modal');
        if (!modal) return;

        modal.classList.add('modal-overlay--closing');
        document.body.style.overflow = '';

        setTimeout(() => {
            modal.classList.add('hidden');
            modal.classList.remove('modal-overlay--closing');
        }, 300);
    }

    function init() {
        const closeBtn = document.getElementById('rx-close');
        const closeFooter = document.getElementById('rx-close-footer');
        const downloadBtn = document.getElementById('rx-download');
        const modal = document.getElementById('rx-modal');

        if (closeBtn) closeBtn.addEventListener('click', close);
        if (closeFooter) closeFooter.addEventListener('click', close);
        if (downloadBtn) {
            downloadBtn.addEventListener('click', () => {
                alert('PDF download will be available when connected to the backend API.');
            });
        }

        // Click overlay to close
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) close();
            });
        }

        // Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal && !modal.classList.contains('hidden')) {
                close();
            }
        });
    }

    function buildPrescriptionHTML(rx) {
        let html = '';

        // Patient Info
        html += rxSection('Patient Information', `
            ${rxField('Name', rx.patient_info.name)}
            ${rxField('Age', rx.patient_info.age + ' years')}
            ${rxField('Gender', rx.patient_info.gender)}
            ${rxField('Date', rx.patient_info.date)}
        `);

        // Diagnosis
        html += rxSection('Diagnosis', `<p class="rx-diagnosis">${escapeHtml(rx.diagnosis)}</p>`);

        // Medications
        let medsHtml = '';
        rx.medication.forEach(med => {
            medsHtml += `<div class="rx-med-card">
                <p class="rx-med-card__name">${escapeHtml(med.name)}</p>
                ${rxField('Dosage', med.dosage_and_route)}
                ${rxField('Frequency', med.frequency_and_duration)}
                ${rxField('Refills', med.refills)}
                ${med.special_instructions ? rxField('Note', med.special_instructions) : ''}
            </div>`;
        });
        html += rxSection('Medications', medsHtml);

        // Recommendations
        let recsHtml = '';
        rx.non_pharmacological_recommendations.forEach(r => {
            recsHtml += `<p class="rx-list-item">${escapeHtml(r.title)}</p>`;
        });
        html += rxSection('Recommendations', recsHtml);

        // Tests
        let testsHtml = '';
        rx.medical_tests.forEach(t => {
            testsHtml += `<p class="rx-list-item">${escapeHtml(t.test_name)}</p>`;
        });
        html += rxSection('Recommended Tests', testsHtml);

        // Prescriber
        html += rxSection('Prescriber', `<p class="rx-prescriber">${escapeHtml(rx.prescriber.name)}</p>`);

        return html;
    }

    function rxSection(title, content) {
        return `<div class="rx-section">
            <div class="rx-section__title">${escapeHtml(title)}</div>
            ${content}
        </div>`;
    }

    function rxField(label, value) {
        return `<div class="rx-field">
            <span class="rx-field__label">${escapeHtml(label)}:</span>
            <span class="rx-field__value">${escapeHtml(value)}</span>
        </div>`;
    }

    return { open, close, init };
})();


/* ═══════════════════════════════════════════════════════════════════════
   12. CHAT INPUT CONTROLLER
   ═══════════════════════════════════════════════════════════════════════ */

const ChatInput = (() => {
    let textarea, sendBtn, inputField;

    function init() {
        textarea = document.getElementById('chat-textarea');
        sendBtn = document.getElementById('send-btn');
        inputField = document.getElementById('input-field');

        if (!textarea || !sendBtn) return;

        textarea.addEventListener('input', handleInput);
        textarea.addEventListener('keydown', handleKeydown);
        sendBtn.addEventListener('click', handleSend);

        updateSendState();
    }

    function handleInput() {
        // Auto-resize
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
        updateSendState();
    }

    function handleKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    }

    async function handleSend() {
        const text = textarea.value.trim();
        const { phase, isProcessing } = ChatState.get();
        if (!text || isProcessing) return;

        addMessage('user', text);
        textarea.value = '';
        textarea.style.height = 'auto';
        updateSendState();
        rerenderChat();

        if (phase === 'symptom') {
            await processSymptoms(text);
        } else if (phase === 'followup') {
            await processFollowUp(text);
        }
    }

    function updateSendState() {
        if (!textarea || !sendBtn) return;
        const { phase, isProcessing } = ChatState.get();
        const isDisabled = isProcessing || phase === 'complete' || phase === 'idle';
        const hasText = textarea.value.trim().length > 0;

        sendBtn.disabled = isDisabled || !hasText;
        textarea.disabled = isDisabled;

        if (inputField) {
            inputField.classList.toggle('disabled', isDisabled);
        }

        // Placeholder
        if (phase === 'complete') {
            textarea.placeholder = 'Consultation complete. Click ＋ for a new session.';
        } else {
            textarea.placeholder = 'Describe your symptoms or answer the question...';
        }
    }

    return { init, updateSendState };
})();


/* ═══════════════════════════════════════════════════════════════════════
   SHARED HELPERS
   ═══════════════════════════════════════════════════════════════════════ */

function addMessage(role, content) {
    const s = ChatState.get();
    s.messages.push({ role, content, time: getTimeStamp() });
}

function rerenderChat() {
    const container = document.getElementById('chat-messages');
    MessageRenderer.render(container);
    ChatInput.updateSendState();
}

function enableInput() {
    const textarea = document.getElementById('chat-textarea');
    if (textarea) textarea.focus();
    ChatInput.updateSendState();
}

function disableInput() {
    ChatInput.updateSendState();
}

function updateHeaderStatus(text) {
    const statusEl = document.querySelector('.chat-header__status');
    if (!statusEl) return;
    // Preserve the dot element, rebuild content
    let dot = statusEl.querySelector('.chat-header__status-dot');
    statusEl.innerHTML = '';
    if (!dot) {
        dot = document.createElement('span');
        dot.className = 'chat-header__status-dot';
    }
    statusEl.appendChild(dot);
    statusEl.append(' ' + text);
}


/* ═══════════════════════════════════════════════════════════════════════
   NEW CHAT
   ═══════════════════════════════════════════════════════════════════════ */

function initNewChat() {
    const btn = document.getElementById('new-chat-btn');
    if (!btn) return;

    btn.addEventListener('click', () => {
        ChatState.reset();
        rerenderChat();

        updateHeaderStatus('Ready to assist');

        // Show form again
        const overlay = document.getElementById('form-overlay');
        if (overlay) {
            overlay.classList.remove('hidden', 'form-overlay--hiding');
        }

        // Reset file uploads
        document.querySelectorAll('.file-upload').forEach(zone => {
            zone.classList.remove('has-file');
        });
        const xrayInput = document.getElementById('xray-file');
        const labInput = document.getElementById('lab-file');
        if (xrayInput) xrayInput.value = '';
        if (labInput) labInput.value = '';

        // Reset form values
        const form = document.getElementById('patient-form');
        if (form) form.reset();

        ChatInput.updateSendState();
    });
}


/* ═══════════════════════════════════════════════════════════════════════
   13. INITIALIZATION
   ═══════════════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    // Theme — init on all pages
    Theme.init();

    // Detect page
    const isLandingPage = document.getElementById('hero') !== null;
    const isChatPage = document.getElementById('chat-main') !== null;

    if (isLandingPage) {
        // Landing page modules
        Particles.generate('particles', 30);
        Navbar.init();
        ScrollAnimator.init();
        SmoothScroll.init();
    }

    if (isChatPage) {
        // Chat page modules
        PatientForm.init();
        FileUpload.init();
        ChatInput.init();
        PrescriptionModal.init();
        initNewChat();
    }
});
