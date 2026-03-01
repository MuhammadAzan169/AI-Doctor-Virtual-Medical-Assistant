/* ═══════════════════════════════════════════════════════════════════════
   AI DOCTOR — VIRTUAL MEDICAL ASSISTANT
   Main Application JavaScript
   
   Modules:
   1. Landing Page — Animations, particles, scroll effects, nav
   2. Chatbot Page — Patient form, chat engine, message rendering,
                     typing indicator, prescription modal, API placeholders
   ═══════════════════════════════════════════════════════════════════════ */

'use strict';

// ─── UTILITY HELPERS ────────────────────────────────────────────────────
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

/** Returns a short timestamp like "2:45 PM" */
function getTimeStamp() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/** Simple delay helper */
function wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/** Escape HTML to prevent XSS in chat messages */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}


// ═══════════════════════════════════════════════════════════════════════
// LANDING PAGE MODULE
// ═══════════════════════════════════════════════════════════════════════

function initLandingPage() {

    // ─── Floating Particles ──────────────────────────────────────
    const particlesContainer = $('#particles');
    if (particlesContainer) {
        const PARTICLE_COUNT = 30;
        for (let i = 0; i < PARTICLE_COUNT; i++) {
            const p = document.createElement('div');
            p.classList.add('particle');
            p.style.left = `${Math.random() * 100}%`;
            p.style.animationDuration = `${8 + Math.random() * 12}s`;
            p.style.animationDelay = `${Math.random() * 10}s`;
            p.style.width = p.style.height = `${2 + Math.random() * 3}px`;
            p.style.opacity = `${0.2 + Math.random() * 0.4}`;
            particlesContainer.appendChild(p);
        }
    }

    // ─── Navbar Scroll Effect ────────────────────────────────────
    const navbar = $('#navbar');
    if (navbar) {
        let lastScroll = 0;
        const handleScroll = () => {
            const scrollY = window.scrollY;
            navbar.classList.toggle('scrolled', scrollY > 50);
            lastScroll = scrollY;
        };
        window.addEventListener('scroll', handleScroll, { passive: true });
        handleScroll(); // initial check
    }

    // ─── Mobile Menu Toggle ──────────────────────────────────────
    const mobileBtn = $('#mobileMenuBtn');
    const navLinks = $('#navLinks');
    if (mobileBtn && navLinks) {
        mobileBtn.addEventListener('click', () => {
            mobileBtn.classList.toggle('active');
            navLinks.classList.toggle('open');
        });
        // Close menu on link click
        $$('.nav-link', navLinks).forEach(link => {
            link.addEventListener('click', () => {
                mobileBtn.classList.remove('active');
                navLinks.classList.remove('open');
            });
        });
    }

    // ─── Scroll Animations (Intersection Observer) ───────────────
    const animatedEls = $$('[data-animate]');
    if (animatedEls.length > 0) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry, index) => {
                if (entry.isIntersecting) {
                    // Stagger the animation for grid items
                    const delay = entry.target.dataset.delay || index * 100;
                    setTimeout(() => {
                        entry.target.classList.add('visible');
                    }, Math.min(delay, 600));
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

        animatedEls.forEach(el => observer.observe(el));
    }

    // ─── Animated Counters ───────────────────────────────────────
    const counters = $$('[data-count]');
    if (counters.length > 0) {
        const counterObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const el = entry.target;
                    const target = parseInt(el.dataset.count, 10);
                    animateCounter(el, 0, target, 1200);
                    counterObserver.unobserve(el);
                }
            });
        }, { threshold: 0.5 });

        counters.forEach(c => counterObserver.observe(c));
    }

    function animateCounter(el, start, end, duration) {
        const startTime = performance.now();
        function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // Ease out cubic
            const eased = 1 - Math.pow(1 - progress, 3);
            el.textContent = Math.round(start + (end - start) * eased);
            if (progress < 1) {
                requestAnimationFrame(update);
            }
        }
        requestAnimationFrame(update);
    }

    // ─── Smooth Scroll for anchor links ──────────────────────────
    $$('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', (e) => {
            const href = anchor.getAttribute('href');
            if (href === '#') return;
            const target = $(href);
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });
}


// ═══════════════════════════════════════════════════════════════════════
// CHATBOT PAGE MODULE
// ═══════════════════════════════════════════════════════════════════════

function initChatbotPage() {

    // ─── DOM References ──────────────────────────────────────────
    const overlay        = $('#patientFormOverlay');
    const form           = $('#patientForm');
    const chatMessages   = $('#chatMessages');
    const chatInput      = $('#chatInput');
    const sendBtn        = $('#sendBtn');
    const typingIndicator = $('#typingIndicator');
    const headerStatus   = $('#headerStatus');
    const newChatBtn     = $('#newChatBtn');

    // File uploads
    const xrayUpload     = $('#xrayUpload');
    const xrayZone       = $('#xrayUploadZone');
    const xrayPreview    = $('#xrayPreview');
    const xrayPreviewImg = $('#xrayPreviewImg');
    const reportUpload   = $('#reportUpload');
    const reportZone     = $('#reportUploadZone');
    const reportPreview  = $('#reportPreview');
    const reportFileName = $('#reportFileName');

    // Prescription modal
    const prescriptionModal   = $('#prescriptionModal');
    const prescriptionContent = $('#prescriptionContent');
    const modalCloseBtn       = $('#modalCloseBtn');
    const modalCloseBtn2      = $('#modalCloseBtn2');
    const downloadPdfBtn      = $('#downloadPdfBtn');

    // ─── Application State ───────────────────────────────────────
    const state = {
        patient: null,          // { name, age, gender }
        xrayFile: null,         // File object
        reportFile: null,       // File object
        messages: [],           // Array of { role: 'user'|'ai'|'system', content: string }
        conversationPhase: 'idle',  // idle | symptom-input | follow-up | complete
        followUpQuestions: [],  // Array of question strings from AI
        currentQuestionIdx: 0,  // Current follow-up question index
        answers: [],            // User answers to follow-up questions
        prescription: null,     // Prescription data object
        isProcessing: false,    // Is AI currently "thinking"
    };

    // ─── FILE UPLOAD HANDLERS ────────────────────────────────────

    function setupFileUpload(zone, input, previewEl, previewImg, fileNameEl, stateKey) {
        // Click to open file dialog
        zone.addEventListener('click', (e) => {
            if (e.target.closest('.file-remove-btn')) return;
            input.click();
        });

        // Drag & drop
        ['dragover', 'dragenter'].forEach(evt => {
            zone.addEventListener(evt, (e) => {
                e.preventDefault();
                zone.classList.add('dragover');
            });
        });
        ['dragleave', 'drop'].forEach(evt => {
            zone.addEventListener(evt, () => {
                zone.classList.remove('dragover');
            });
        });
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file) handleFile(file);
        });

        // Input change
        input.addEventListener('change', () => {
            const file = input.files[0];
            if (file) handleFile(file);
        });

        function handleFile(file) {
            state[stateKey] = file;
            const content = zone.querySelector('.file-upload-content');
            if (content) content.hidden = true;
            previewEl.hidden = false;

            if (previewImg && file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = (e) => { previewImg.src = e.target.result; };
                reader.readAsDataURL(file);
            }
            if (fileNameEl) {
                fileNameEl.textContent = file.name;
            }
        }

        // Remove button
        const removeBtn = zone.querySelector('.file-remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                state[stateKey] = null;
                input.value = '';
                previewEl.hidden = true;
                const content = zone.querySelector('.file-upload-content');
                if (content) content.hidden = false;
            });
        }
    }

    if (xrayZone) {
        setupFileUpload(xrayZone, xrayUpload, xrayPreview, xrayPreviewImg, null, 'xrayFile');
    }
    if (reportZone) {
        setupFileUpload(reportZone, reportUpload, reportPreview, null, reportFileName, 'reportFile');
    }

    // ─── PATIENT FORM SUBMISSION ─────────────────────────────────

    if (form) {
        form.addEventListener('submit', (e) => {
            e.preventDefault();

            const name   = $('#patientName').value.trim();
            const age    = $('#patientAge').value.trim();
            const gender = $('#patientGender').value;

            if (!name || !age || !gender) return;

            state.patient = { name, age, gender };
            state.conversationPhase = 'symptom-input';

            // Hide form overlay with animation
            overlay.style.animation = 'overlayOut 0.3s ease forwards';
            setTimeout(() => {
                overlay.classList.add('hidden');
            }, 300);

            // Enable chat input
            chatInput.disabled = false;
            sendBtn.disabled = false;
            chatInput.focus();

            // Set header status
            headerStatus.textContent = 'Consultation active';

            // Welcome message from AI
            const welcomeMsg = `Hello, ${escapeHtml(name)}! I'm your AI Doctor. 👋\n\nI can see you're ${age} years old. Welcome to your virtual medical consultation.\n\n${state.xrayFile ? '📸 I received your X-ray image — I\'ll analyze it as part of the consultation.\n' : ''}${state.reportFile ? '📋 I received your medical test report — I\'ll include its findings.\n' : ''}\nPlease describe your symptoms in detail so I can begin the assessment.`;

            addMessage('ai', welcomeMsg);

            // System message
            addSystemMessage('Consultation started — describe your symptoms below');
        });
    }

    // ─── MESSAGE RENDERING ───────────────────────────────────────

    /**
     * Adds a message to the chat UI and state
     * @param {'ai'|'user'|'system'} role
     * @param {string} content
     */
    function addMessage(role, content) {
        state.messages.push({ role, content, time: getTimeStamp() });

        if (role === 'system') {
            addSystemMessage(content);
            return;
        }

        const msgEl = document.createElement('div');
        msgEl.className = `chat-msg chat-msg--${role}`;

        const avatar = role === 'ai' ? '🩺' : '👤';
        const bubbleContent = formatMessageContent(content);

        msgEl.innerHTML = `
            <div class="msg-avatar">${avatar}</div>
            <div class="msg-content">
                <div class="msg-bubble">${bubbleContent}</div>
                <span class="msg-time">${getTimeStamp()}</span>
            </div>
        `;

        chatMessages.appendChild(msgEl);
        scrollToBottom();
    }

    /**
     * Adds a system/info message (centered pill)
     */
    function addSystemMessage(text) {
        const el = document.createElement('div');
        el.className = 'chat-system-msg';
        el.innerHTML = `<span class="system-pill">${escapeHtml(text)}</span>`;
        chatMessages.appendChild(el);
        scrollToBottom();
    }

    /**
     * Format message content — convert newlines and basic markdown-like bold
     */
    function formatMessageContent(text) {
        let html = escapeHtml(text);
        // Convert **bold** to <strong>
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        // Convert newlines to <br>
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    /**
     * Smooth scroll to bottom of chat
     */
    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        });
    }

    /**
     * Show/hide typing indicator
     */
    function showTyping(show) {
        typingIndicator.hidden = !show;
        if (show) {
            headerStatus.textContent = 'AI Doctor is thinking...';
            scrollToBottom();
        } else {
            headerStatus.textContent = 'Consultation active';
        }
    }

    // ─── SEND MESSAGE HANDLER ────────────────────────────────────

    function handleSend() {
        const text = chatInput.value.trim();
        if (!text || state.isProcessing) return;

        addMessage('user', text);
        chatInput.value = '';
        autoResizeInput();

        // Route based on conversation phase
        switch (state.conversationPhase) {
            case 'symptom-input':
                processSymptoms(text);
                break;
            case 'follow-up':
                processFollowUpAnswer(text);
                break;
            default:
                processGenericMessage(text);
        }
    }

    // Send button click
    if (sendBtn) {
        sendBtn.addEventListener('click', handleSend);
    }

    // Enter key (Shift+Enter for newline)
    if (chatInput) {
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
            }
        });

        // Auto-resize textarea
        chatInput.addEventListener('input', autoResizeInput);
    }

    function autoResizeInput() {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    }

    // ─── CONVERSATION LOGIC (with API placeholders) ──────────────

    /**
     * Process initial symptom description
     * In production: sends to /api/generate-questions with patient info + symptoms
     */
    async function processSymptoms(symptomText) {
        state.isProcessing = true;
        disableInput();
        showTyping(true);

        // ── API PLACEHOLDER ──────────────────────────────────────
        // In production, this would call:
        // POST /api/generate-questions
        // Body: { patient: state.patient, symptoms: symptomText, xray: state.xrayFile, report: state.reportFile }
        // Response: { questions: [...], fracture_status: "..." }
        //
        // For now, simulate AI generating follow-up questions:
        await wait(2000 + Math.random() * 1500);

        const simulatedQuestions = generateSimulatedQuestions(symptomText);
        state.followUpQuestions = simulatedQuestions;
        state.currentQuestionIdx = 0;
        state.answers = [];
        state.conversationPhase = 'follow-up';

        showTyping(false);

        // If X-ray was uploaded, show a simulated analysis message
        if (state.xrayFile) {
            addMessage('ai', `🩻 **X-Ray Analysis:** I've processed your uploaded X-ray image. The AI fracture detection model has analyzed the image, and I'll incorporate the findings into the diagnosis.\n\nNow, I need to ask you some follow-up questions to better understand your condition.`);
            await wait(1000);
        }

        // If report was uploaded
        if (state.reportFile) {
            addMessage('ai', `📋 **Test Report Received:** Your medical test report has been processed via OCR, and the extracted data will be considered in the assessment.`);
            await wait(1000);
        }

        // Ask first question
        askNextQuestion();

        state.isProcessing = false;
        enableInput();
    }

    /**
     * Process answer to a follow-up question
     */
    async function processFollowUpAnswer(answerText) {
        state.answers.push(answerText);
        state.currentQuestionIdx++;

        if (state.currentQuestionIdx < state.followUpQuestions.length) {
            // Ask next question
            state.isProcessing = true;
            disableInput();
            showTyping(true);
            await wait(800 + Math.random() * 800);
            showTyping(false);
            askNextQuestion();
            state.isProcessing = false;
            enableInput();
        } else {
            // All questions answered — generate prescription
            addSystemMessage('All follow-up questions answered ✅');
            await generatePrescription();
        }
    }

    /**
     * Ask the next follow-up question
     */
    function askNextQuestion() {
        const q = state.followUpQuestions[state.currentQuestionIdx];
        const questionNum = state.currentQuestionIdx + 1;
        const totalQuestions = state.followUpQuestions.length;
        addMessage('ai', `**Question ${questionNum} of ${totalQuestions}:**\n\n${q}`);
    }

    /**
     * Handle generic message when conversation is in other states
     */
    async function processGenericMessage(text) {
        state.isProcessing = true;
        disableInput();
        showTyping(true);
        await wait(1500);
        showTyping(false);
        addMessage('ai', 'Thank you for your message. If you\'d like to start a new consultation, please click the ＋ button at the top right.');
        state.isProcessing = false;
        enableInput();
    }

    /**
     * Generate prescription after all follow-up answers collected
     * In production: POST /api/generate-prescription
     */
    async function generatePrescription() {
        state.isProcessing = true;
        disableInput();
        showTyping(true);
        headerStatus.textContent = 'Generating prescription...';

        // ── API PLACEHOLDER ──────────────────────────────────────
        // POST /api/generate-prescription
        // Body: { patient: state.patient, symptoms, qna, xray_result, report_ocr }
        // Response: { prescription: {...}, reasoning: "..." }
        await wait(3000 + Math.random() * 2000);

        showTyping(false);

        // Simulated prescription
        const prescription = generateSimulatedPrescription();
        state.prescription = prescription;
        state.conversationPhase = 'complete';

        // AI reasoning message
        addMessage('ai', `Based on my analysis of your symptoms, your answers to the follow-up questions${state.xrayFile ? ', the X-ray findings' : ''}${state.reportFile ? ', and your medical test results' : ''}, I've prepared a comprehensive medical prescription for you.\n\n**Diagnosis:** ${prescription.diagnosis}\n\nPlease review the full prescription below. Remember, this is an AI-generated assessment — always consult a qualified healthcare provider for confirmation.`);

        // Add prescription button inside chat
        const btnContainer = document.createElement('div');
        btnContainer.className = 'chat-msg chat-msg--ai';
        btnContainer.innerHTML = `
            <div class="msg-avatar">🩺</div>
            <div class="msg-content">
                <div class="msg-bubble">
                    <strong>📋 Your prescription is ready!</strong><br><br>
                    You can view the complete prescription with medications, recommendations, and tests below.
                    <div class="msg-prescription-btn">
                        <button class="btn btn-primary" id="viewPrescriptionBtn">
                            <span>View Prescription</span>
                        </button>
                    </div>
                </div>
            </div>
        `;
        chatMessages.appendChild(btnContainer);
        scrollToBottom();

        // Bind prescription view button
        const viewBtn = $('#viewPrescriptionBtn');
        if (viewBtn) {
            viewBtn.addEventListener('click', () => showPrescriptionModal(prescription));
        }

        addSystemMessage('Consultation complete — You can start a new one anytime');
        headerStatus.textContent = 'Consultation complete';

        state.isProcessing = false;
        // Keep input disabled after completion
        chatInput.placeholder = 'Consultation complete. Click ＋ for a new session.';
    }

    // ─── PRESCRIPTION MODAL ──────────────────────────────────────

    function showPrescriptionModal(rx) {
        if (!prescriptionModal || !prescriptionContent) return;

        prescriptionContent.innerHTML = renderPrescriptionHTML(rx);
        prescriptionModal.hidden = false;
    }

    function hidePrescriptionModal() {
        if (prescriptionModal) prescriptionModal.hidden = true;
    }

    if (modalCloseBtn) modalCloseBtn.addEventListener('click', hidePrescriptionModal);
    if (modalCloseBtn2) modalCloseBtn2.addEventListener('click', hidePrescriptionModal);

    // Close modal on overlay click
    if (prescriptionModal) {
        prescriptionModal.addEventListener('click', (e) => {
            if (e.target === prescriptionModal) hidePrescriptionModal();
        });
    }

    // Download PDF placeholder
    if (downloadPdfBtn) {
        downloadPdfBtn.addEventListener('click', () => {
            // ── API PLACEHOLDER ──────────────────────────────
            // In production: GET /api/download-prescription-pdf
            // For now, show a message
            alert('PDF download will be available when connected to the backend API.\n\nThe backend uses ReportLab to generate professional PDF prescriptions.');
        });
    }

    /**
     * Render prescription data as HTML for the modal
     */
    function renderPrescriptionHTML(rx) {
        let html = '';

        // Patient Info
        html += `
            <div class="rx-section">
                <div class="rx-section-title">Patient Information</div>
                <div class="rx-field"><span class="rx-field-label">Name:</span> <span class="rx-field-value">${escapeHtml(rx.patient_info.name)}</span></div>
                <div class="rx-field"><span class="rx-field-label">Age:</span> <span class="rx-field-value">${rx.patient_info.age} years</span></div>
                <div class="rx-field"><span class="rx-field-label">Gender:</span> <span class="rx-field-value">${escapeHtml(rx.patient_info.gender)}</span></div>
                <div class="rx-field"><span class="rx-field-label">Date:</span> <span class="rx-field-value">${escapeHtml(rx.patient_info.date)}</span></div>
            </div>
        `;

        // Diagnosis
        html += `
            <div class="rx-section">
                <div class="rx-section-title">Diagnosis</div>
                <p style="color: var(--neutral-200); font-size: 0.9rem; line-height: 1.6;">${escapeHtml(rx.diagnosis)}</p>
            </div>
        `;

        // Medications
        if (rx.medication && rx.medication.length > 0) {
            html += `<div class="rx-section"><div class="rx-section-title">Medications</div>`;
            rx.medication.forEach(med => {
                html += `
                    <div class="rx-med-card">
                        <div class="rx-med-name">${escapeHtml(med.name)}</div>
                        <div class="rx-field"><span class="rx-field-label">Dosage:</span> <span class="rx-field-value">${escapeHtml(med.dosage_and_route)}</span></div>
                        <div class="rx-field"><span class="rx-field-label">Frequency:</span> <span class="rx-field-value">${escapeHtml(med.frequency_and_duration)}</span></div>
                        <div class="rx-field"><span class="rx-field-label">Refills:</span> <span class="rx-field-value">${escapeHtml(med.refills)}</span></div>
                        ${med.special_instructions ? `<div class="rx-field"><span class="rx-field-label">Note:</span> <span class="rx-field-value">${escapeHtml(med.special_instructions)}</span></div>` : ''}
                    </div>
                `;
            });
            html += `</div>`;
        }

        // Non-pharmacological recommendations
        if (rx.non_pharmacological_recommendations && rx.non_pharmacological_recommendations.length > 0) {
            html += `<div class="rx-section"><div class="rx-section-title">Recommendations</div>`;
            rx.non_pharmacological_recommendations.forEach(rec => {
                html += `<div class="rx-rec-item">${escapeHtml(rec.title)}</div>`;
            });
            html += `</div>`;
        }

        // Medical tests
        if (rx.medical_tests && rx.medical_tests.length > 0) {
            html += `<div class="rx-section"><div class="rx-section-title">Recommended Tests</div>`;
            rx.medical_tests.forEach(test => {
                html += `<div class="rx-test-item">${escapeHtml(test.test_name)}</div>`;
            });
            html += `</div>`;
        }

        // Prescriber
        html += `
            <div class="rx-section">
                <div class="rx-section-title">Prescriber</div>
                <p style="color: var(--neutral-200); font-size: 0.9rem;">${escapeHtml(rx.prescriber.name)}</p>
            </div>
        `;

        return html;
    }


    // ─── NEW CHAT ────────────────────────────────────────────────
    if (newChatBtn) {
        newChatBtn.addEventListener('click', () => {
            if (state.conversationPhase !== 'idle' && state.conversationPhase !== 'complete') {
                if (!confirm('Are you sure you want to start a new consultation? Current progress will be lost.')) {
                    return;
                }
            }
            resetChat();
        });
    }

    function resetChat() {
        // Reset state
        state.patient = null;
        state.xrayFile = null;
        state.reportFile = null;
        state.messages = [];
        state.conversationPhase = 'idle';
        state.followUpQuestions = [];
        state.currentQuestionIdx = 0;
        state.answers = [];
        state.prescription = null;
        state.isProcessing = false;

        // Clear chat UI
        chatMessages.innerHTML = '';

        // Reset input
        chatInput.value = '';
        chatInput.disabled = true;
        chatInput.placeholder = 'Describe your symptoms or answer the question...';
        sendBtn.disabled = true;

        // Reset header
        headerStatus.textContent = 'Ready to assist';

        // Reset file uploads
        [xrayUpload, reportUpload].forEach(input => { if (input) input.value = ''; });
        if (xrayPreview) xrayPreview.hidden = true;
        if (reportPreview) reportPreview.hidden = true;
        const xrayContent = xrayZone ? xrayZone.querySelector('.file-upload-content') : null;
        const reportContent = reportZone ? reportZone.querySelector('.file-upload-content') : null;
        if (xrayContent) xrayContent.hidden = false;
        if (reportContent) reportContent.hidden = false;

        // Reset form
        if (form) form.reset();

        // Show form overlay
        overlay.classList.remove('hidden');
        overlay.style.animation = 'overlayIn 0.4s ease forwards';
    }

    // ─── INPUT ENABLE / DISABLE ──────────────────────────────────
    function disableInput() {
        chatInput.disabled = true;
        sendBtn.disabled = true;
    }

    function enableInput() {
        chatInput.disabled = false;
        sendBtn.disabled = false;
        chatInput.focus();
    }


    // ─── SIMULATED DATA (Replace with real API calls) ────────────

    /**
     * Generate simulated follow-up questions based on symptoms
     * In production: this comes from the LLM via the backend
     */
    function generateSimulatedQuestions(symptoms) {
        // These simulate the AI doctor asking 7+ follow-up questions
        return [
            'On a scale of 1 to 10, how would you rate the severity of your symptoms?',
            'When did you first start experiencing these symptoms? Can you provide a specific date or approximate duration?',
            'Have you experienced similar symptoms before in the past? If so, when and how were they managed?',
            'Are you currently taking any medications, vitamins, or supplements? Please list all of them.',
            'Do you have any known allergies, especially to medications?',
            'Do you have any pre-existing medical conditions such as diabetes, hypertension, asthma, or heart disease?',
            'Have you noticed any other symptoms accompanying your main complaint, such as fever, fatigue, nausea, or changes in appetite?',
            'Is there any family history of relevant medical conditions that you are aware of?',
        ];
    }

    /**
     * Generate simulated prescription data
     * In production: this comes from the LLM via the backend
     * Follows the exact structure used by json_builder.py and pdf_builder.py
     */
    function generateSimulatedPrescription() {
        const today = new Date().toLocaleDateString('en-US', {
            year: 'numeric', month: 'long', day: 'numeric'
        });

        return {
            patient_info: {
                name: state.patient.name,
                age: parseInt(state.patient.age),
                gender: state.patient.gender,
                date: today
            },
            diagnosis: 'This is a simulated diagnosis. When connected to the backend, the AI will provide a detailed clinical diagnosis based on your symptoms, follow-up answers, and any uploaded medical files.',
            medication: [
                {
                    name: 'Simulated Medication (Example Brand)',
                    brand_names: [],
                    dosage_and_route: '500mg orally',
                    frequency_and_duration: 'Twice daily for 7 days',
                    refills: 'None',
                    special_instructions: 'Take with food. This is a placeholder medication for demonstration purposes.'
                },
                {
                    name: 'Vitamin D3 Supplement (e.g., Sunny-D)',
                    brand_names: [],
                    dosage_and_route: '2000 IU orally',
                    frequency_and_duration: 'Once daily for 30 days',
                    refills: '2 refills',
                    special_instructions: 'Take with a meal containing fat for better absorption.'
                }
            ],
            non_pharmacological_recommendations: [
                { title: 'Maintain adequate hydration — drink at least 8 glasses of water daily.', details: { text: '' } },
                { title: 'Ensure 7-8 hours of quality sleep each night.', details: { text: '' } },
                { title: 'Incorporate light physical activity such as walking for 30 minutes daily.', details: { text: '' } },
                { title: 'Avoid processed foods and maintain a balanced diet rich in fruits and vegetables.', details: { text: '' } },
            ],
            medical_tests: [
                { test_name: 'Complete Blood Count (CBC)', details: { text: '' } },
                { test_name: 'Vitamin D and B12 levels', details: { text: '' } },
            ],
            prescriber: {
                name: 'Dr. AI Medic. MD'
            }
        };
    }

    // ─── KEYBOARD SHORTCUT: Escape to close modal ───────────────
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            hidePrescriptionModal();
        }
    });
}


// ═══════════════════════════════════════════════════════════════════════
// PAGE ROUTER — Detect which page and init appropriate module
// ═══════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    const isLandingPage = document.body.classList.contains('landing-page');
    const isChatbotPage = document.body.classList.contains('chatbot-page');

    if (isLandingPage) {
        initLandingPage();
    }

    if (isChatbotPage) {
        initChatbotPage();
    }

    // ─── Add overlayOut animation to CSS dynamically ─────────────
    const style = document.createElement('style');
    style.textContent = `
        @keyframes overlayOut {
            from { opacity: 1; }
            to   { opacity: 0; }
        }
    `;
    document.head.appendChild(style);
});
