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
   10. Prescription Modal
   11. Chat Input Controller
   12. Initialization
   ═══════════════════════════════════════════════════════════════════════ */

'use strict';

// API base — injected at build time via /js/config.js (window.APP_CONFIG).
// Empty string means "same origin". Lets the static bundle target a remote API.
const API_BASE = ((window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) || '').replace(/\/+$/, '');
function apiUrl(path) {
    return API_BASE + (path.startsWith('/') ? path : '/' + path);
}

// Global session tracking
let sessionId = null;
let currentPhase = 'idle';

// Server feature flags populated by /health on load
let appFeatures = { fracture_detection: true, ocr: true, voice: false };

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
   6. HEALTH CHECK
   ═══════════════════════════════════════════════════════════════════════ */

const HealthCheck = (() => {
    async function run() {
        try {
            // 10 s timeout — Render free tier may be sleeping; don't block the UI
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 10000);
            const res = await fetch(apiUrl('/health'), { signal: controller.signal });
            clearTimeout(timer);
            if (res.ok) {
                const data = await res.json();
                if (data.features) appFeatures = data.features;
            }
        } catch {
            // Timed out or unreachable — keep defaults, mic stays hidden
        }
        applyFeatureFlags();
    }

    function applyFeatureFlags() {
        // Upload fields are always visible — the server accepts them regardless of
        // whether fracture detection / OCR are active on this deployment.
        const micBtn = document.getElementById('mic-btn');
        if (micBtn) micBtn.style.display = appFeatures.voice ? '' : 'none';
    }

    return { run };
})();


/* ═══════════════════════════════════════════════════════════════════════
   7. CHAT STATE MACHINE
   ═══════════════════════════════════════════════════════════════════════ */

const ChatState = (() => {
    let state = {
        phase: 'idle',       // idle | active (phase driven by backend)
        patient: null,       // { name, age, gender }
        messages: [],        // [{ role, content, time }]
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
            xrayFile: null,
            reportFile: null,
            prescription: null,
            isProcessing: false,
        };
        // Also reset global session variables
        sessionId = null;
        currentPhase = 'idle';
    }

    return { get, set, reset };
})();


/* ═══════════════════════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════════════════════ */

function getTimeStamp() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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

        const meta = document.createElement('div');
        meta.className = 'chat-msg__meta';

        const time = document.createElement('span');
        time.className = 'chat-msg__time';
        time.textContent = msg.time;
        meta.appendChild(time);

        if (isAi) {
            const speakBtn = document.createElement('button');
            speakBtn.className = 'chat-msg__speak';
            speakBtn.setAttribute('aria-label', 'Listen to message');
            speakBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>';
            speakBtn.addEventListener('click', () => playTTS(msg.content, speakBtn));
            meta.appendChild(speakBtn);
        }

        body.appendChild(bubble);
        body.appendChild(meta);

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
        value = Math.max(1, Math.min(120, value));
        input.value = value;
    }

    function showFormError(msg) {
        const el = document.getElementById('form-error');
        if (!el) return;
        el.textContent = msg;
        el.classList.remove('hidden');
    }

    function clearFormError() {
        const el = document.getElementById('form-error');
        if (el) el.classList.add('hidden');
    }

    async function handleSubmit(e) {
        e.preventDefault();
        const name = document.getElementById('patient-name').value.trim();
        const age = document.getElementById('patient-age').value.trim();
        const gender = document.getElementById('patient-gender').value;

        if (!name || !age || !gender) {
            showFormError('Please fill in all required fields.');
            return;
        }

        clearFormError();

        const { xrayFile, reportFile } = ChatState.get();

        // Store patient info locally
        ChatState.set({ patient: { name, age, gender } });

        // Prepare FormData
        const formData = new FormData();
        formData.append('name', name);
        formData.append('age', parseInt(age, 10));
        formData.append('gender', gender);
        if (xrayFile) formData.append('xray', xrayFile);
        if (reportFile) formData.append('report', reportFile);

        // Show loading state on submit button
        const submitBtn = document.getElementById('form-submit-btn');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Connecting...';
        }

        ChatState.set({ isProcessing: true });
        rerenderChat();

        // After 8 s warn the user the server is cold-starting (Render free tier)
        const wakeupTimer = setTimeout(() => {
            if (submitBtn) submitBtn.textContent = 'Waking up server...';
            showFormError('The server is starting up after inactivity — this takes up to 50 seconds on first use. Please keep waiting...');
        }, 8000);

        try {
            const res = await fetch(apiUrl('/api/start-consultation'), {
                method: 'POST',
                body: formData
            });

            clearTimeout(wakeupTimer);

            if (!res.ok) {
                throw new Error(`Server returned ${res.status}`);
            }

            clearFormError();
            const data = await res.json();
            sessionId = data.session_id;
            currentPhase = data.phase;

            // Update ChatState phase
            ChatState.set({ phase: data.phase, isProcessing: false });

            // Hide form with animation
            const overlay = document.getElementById('form-overlay');
            overlay.classList.add('form-overlay--hiding');
            setTimeout(() => {
                overlay.classList.add('hidden');
                overlay.classList.remove('form-overlay--hiding');
            }, 300);

            // Update header
            updateHeaderStatus('Consultation active');

            // Add the initial AI message from the backend
            addMessage('ai', data.message);
            rerenderChat();
            enableInput();
        } catch (error) {
            clearTimeout(wakeupTimer);
            console.error('Failed to start consultation:', error);
            ChatState.set({ isProcessing: false });
            showFormError('Could not connect. If this is your first visit today, the server may still be waking up — wait a moment and try again.');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/></svg> Start Consultation <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>`;
            }
        }
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
   11. PRESCRIPTION MODAL
   ═══════════════════════════════════════════════════════════════════════ */

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
                if (sessionId) {
                    window.open(apiUrl(`/api/prescription/${sessionId}`), '_blank');
                } else {
                    alert('No active session to download prescription.');
                }
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
   VOICE INPUT
   ═══════════════════════════════════════════════════════════════════════ */

const VoiceInput = (() => {
    let mediaRecorder = null;
    let audioChunks   = [];
    let isRecording   = false;

    function init() {
        const btn = document.getElementById('mic-btn');
        if (!btn) return;
        btn.addEventListener('click', toggle);
    }

    async function toggle() {
        if (isRecording) { stop(); } else { await start(); }
    }

    async function start() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioChunks = [];
            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.addEventListener('dataavailable', e => audioChunks.push(e.data));
            mediaRecorder.addEventListener('stop', sendAudio);
            mediaRecorder.start();
            isRecording = true;
            document.getElementById('mic-btn')?.classList.add('recording');
        } catch (err) {
            console.error('Mic access denied:', err);
            addMessage('ai', 'Could not access your microphone. Please check browser permissions and try again.');
            rerenderChat();
        }
    }

    function stop() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            mediaRecorder.stream.getTracks().forEach(t => t.stop());
        }
        isRecording = false;
        document.getElementById('mic-btn')?.classList.remove('recording');
    }

    async function sendAudio() {
        const blob = new Blob(audioChunks, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append('audio', blob, 'recording.webm');

        const micBtn = document.getElementById('mic-btn');
        if (micBtn) micBtn.disabled = true;

        try {
            const res = await fetch(apiUrl('/api/voice-input'), { method: 'POST', body: formData });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const textarea = document.getElementById('chat-textarea');
            if (textarea && data.text) {
                textarea.value = data.text;
                textarea.dispatchEvent(new Event('input'));
                textarea.focus();
            }
        } catch (err) {
            console.error('Voice transcription failed:', err);
            addMessage('ai', 'Voice transcription failed. Please type your message instead.');
            rerenderChat();
        } finally {
            if (micBtn) micBtn.disabled = false;
        }
    }

    return { init };
})();


/* ═══════════════════════════════════════════════════════════════════════
   TTS HELPER
   ═══════════════════════════════════════════════════════════════════════ */

async function playTTS(text, btn) {
    btn.disabled = true;
    const formData = new FormData();
    formData.append('text', text);
    try {
        const res = await fetch(apiUrl('/api/tts'), { method: 'POST', body: formData });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const audioUrl = URL.createObjectURL(blob);
        const audio = new Audio(audioUrl);
        audio.play();
        audio.onended = () => {
            URL.revokeObjectURL(audioUrl);
            btn.disabled = false;
        };
    } catch (err) {
        console.error('TTS failed:', err);
        btn.disabled = false;
    }
}


/* ═══════════════════════════════════════════════════════════════════════
   Helper: Show Prescription Download Button (kept for direct-download fallback)
   ═══════════════════════════════════════════════════════════════════════ */

function showPrescriptionDownload(sid) {
    // Remove any existing download button first
    const existing = document.querySelector('.prescription-download-btn');
    if (existing) existing.remove();

    const downloadBtn = document.createElement('button');
    downloadBtn.className = 'prescription-download-btn';
    downloadBtn.textContent = '📥 Download Prescription PDF';
    downloadBtn.onclick = () => window.open(apiUrl(`/api/prescription/${sid}`), '_blank');

    // Append to chat area (e.g., after the last message)
    const chatContainer = document.getElementById('chat-messages');
    if (chatContainer) {
        const wrapper = document.createElement('div');
        wrapper.className = 'chat-msg chat-msg--ai';
        wrapper.appendChild(downloadBtn);
        chatContainer.appendChild(wrapper);
        MessageRenderer.scrollToBottom(chatContainer.parentElement);
    }
}


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
        const { isProcessing } = ChatState.get();
        if (!text || isProcessing || !sessionId) return;

        // Add user message immediately
        addMessage('user', text);
        textarea.value = '';
        textarea.style.height = 'auto';
        updateSendState();
        rerenderChat();

        // Show processing indicator
        ChatState.set({ isProcessing: true });
        rerenderChat();

        // After 8 s add a system notice about Render cold starts
        const wakeupTimer = setTimeout(() => {
            if (ChatState.get().isProcessing) {
                addMessage('system', 'Server is starting up after inactivity — please wait up to 50 seconds...');
                rerenderChat();
            }
        }, 8000);

        let res;
        try {
            res = await fetch(apiUrl('/api/chat'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, message: text })
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            clearTimeout(wakeupTimer);
            const data = await res.json();
            addMessage('ai', data.message);

            currentPhase = data.phase;
            ChatState.set({ phase: data.phase });

            if (data.prescription_ready && data.prescription) {
                ChatState.set({ prescription: data.prescription });
            }

            ChatState.set({ isProcessing: false });
            rerenderChat();
        } catch (error) {
            clearTimeout(wakeupTimer);
            console.error('Chat error:', error);
            ChatState.set({ isProcessing: false });

            let errorMsg = 'Sorry, an error occurred. Please try again.';
            if (res) {
                if (res.status === 404) {
                    errorMsg = 'Your session has expired. Please start a new consultation by clicking the + button.';
                } else if (res.status === 503) {
                    errorMsg = 'This feature is currently unavailable on the server. Please try again later.';
                }
            }
            addMessage('ai', errorMsg);
            rerenderChat();
        }
    }

    function updateSendState() {
        if (!textarea || !sendBtn) return;
        const { isProcessing, phase } = ChatState.get();
        const isDisabled = isProcessing || phase === 'complete' || !sessionId;
        const hasText = textarea.value.trim().length > 0;

        sendBtn.disabled = isDisabled || !hasText;
        textarea.disabled = isDisabled;

        if (inputField) {
            inputField.classList.toggle('disabled', isDisabled);
        }

        // Placeholder
        if (phase === 'complete') {
            textarea.placeholder = 'Consultation complete. Click ＋ for a new session.';
        } else if (!sessionId) {
            textarea.placeholder = 'Please start a consultation first.';
        } else {
            textarea.placeholder = 'Type your message...';
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
            const nameEl = zone.querySelector('.file-upload__filename');
            if (nameEl) nameEl.textContent = '';
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
        HealthCheck.run();
        PatientForm.init();
        FileUpload.init();
        ChatInput.init();
        PrescriptionModal.init();
        VoiceInput.init();
        initNewChat();
    }
});