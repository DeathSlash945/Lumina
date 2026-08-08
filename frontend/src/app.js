import { generateCurriculum, updateStepProgress, mutateCurriculum, getUserGroqKey, setUserGroqKey } from './api.js';

const STORAGE_KEY = 'lumina_saved_paths';

let currentPath = null;
let expandedSteps = new Set();
let sidebarOpen = true;

// dom element refs
const form = document.getElementById('generator-form');
const submitBtn = document.getElementById('submit-btn');
const outputContainer = document.getElementById('output-container');
const sidebar = document.getElementById('sidebar');
const sidebarList = document.getElementById('sidebar-list');
const sidebarToggle = document.getElementById('sidebar-toggle');
const progressWrap = document.getElementById('progress-wrap');
const progressLabel = document.getElementById('progress-label');
const progressPercent = document.getElementById('progress-percent');
const progressFill = document.getElementById('progress-fill');
const settingsToggle = document.getElementById('settings-toggle');
const settingsPanel = document.getElementById('settings-panel');
const groqKeyInput = document.getElementById('groq-key-input');
const groqKeySave = document.getElementById('groq-key-save');
const groqKeyClear = document.getElementById('groq-key-clear');
const groqKeyStatus = document.getElementById('groq-key-status');
const relatedWrap = document.getElementById('related-topics-wrap');
const relatedList = document.getElementById('related-topics-list');

const mutationWrap = document.getElementById('mutation-wrap');
const mutationForm = document.getElementById('mutation-form');
const mutationInput = document.getElementById('mutation-input');
const mutationBtn = document.getElementById('mutation-btn');

// local storage handlers
function loadSavedPaths() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        return raw ? JSON.parse(raw) : {};
    } catch {
        return {};
    }
}

function saveSavedPaths(paths) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(paths));
}

function persistCurrentPath() {
    if (!currentPath) return;
    const paths = loadSavedPaths();
    paths[currentPath.main_topic] = {
        ...currentPath,
        _savedAt: paths[currentPath.main_topic]?._savedAt || Date.now(),
    };
    saveSavedPaths(paths);
    renderSidebar();
}

// removes the path from saved paths
function deleteSavedPath(topic) {
    const paths = loadSavedPaths();
    delete paths[topic];
    saveSavedPaths(paths);
    if (currentPath && currentPath.main_topic === topic) {
        currentPath = null;
        outputContainer.innerHTML = '';
        updateProgressBar();
    }
    renderSidebar();
}

// data normalization helpers
function normalizeStep(step, index) {
    const title = step.title || step.step_title || step.name || `Step ${index + 1}`;
    const resources = (step.resources || []).map(res => ({
        ...res,
        completed: !!res.completed,
    }));
    return { ...step, title, resources };
}

function normalizePath(path) {
    return {
        ...path,
        steps: (path.steps || []).map(normalizeStep),
    };
}

// sidebar list rendering
function renderSidebar() {
    const paths = loadSavedPaths();
    const entries = Object.values(paths).sort((a, b) => (b._savedAt || 0) - (a._savedAt || 0));

    if (!entries.length) {
        sidebarList.innerHTML = `<p class="text-xs px-2 py-4 text-center" style="color: var(--text-muted);">No saved paths yet.</p>`;
        return;
    }

    sidebarList.innerHTML = entries.map(p => {
        const total = (p.steps || []).length;
        const done = (p.steps || []).filter(s => s.status === 'completed').length;
        const isActive = currentPath && currentPath.main_topic === p.main_topic;
        return `
            <div data-topic="${escapeAttr(p.main_topic)}"
                 class="sidebar-item flat-btn group flex items-center justify-between gap-2 px-3 py-2.5 cursor-pointer border"
                 style="background: ${isActive ? 'var(--bg-panel-2)' : 'transparent'}; border-color: ${isActive ? 'var(--purple-mid)' : 'transparent'};">
                <div class="min-w-0">
                    <p class="text-sm font-medium truncate" style="color: var(--text-primary);">${escapeHtml(p.main_topic)}</p>
                    <p class="text-[11px]" style="color: var(--text-muted);">${done}/${total} steps complete</p>
                </div>
                <button data-delete-topic="${escapeAttr(p.main_topic)}"
                        class="delete-path-btn flex-shrink-0 opacity-0 group-hover:opacity-100 text-xs px-1.5 py-1 hover:bg-red-950/40 hover:text-red-400"
                        style="color: var(--text-muted);" title="Delete Path">✕</button>
            </div>
        `;
    }).join('');

    sidebarList.querySelectorAll('.sidebar-item').forEach(el => {
        el.addEventListener('click', (e) => {
            if (e.target.closest('.delete-path-btn')) return;
            const topic = el.dataset.topic;
            const paths = loadSavedPaths();
            if (paths[topic]) {
                currentPath = normalizePath(paths[topic]);
                expandedSteps = new Set();
                document.getElementById('topic-input').value = topic;
                renderCurriculum();
                renderSidebar();
            }
        });
    });

    sidebarList.querySelectorAll('.delete-path-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteSavedPath(btn.dataset.deleteTopic);
        });
    });
}

function renderRelatedTopics() {
    const topics = currentPath?.related_topics || [];
    if (!topics.length) {
        relatedWrap.classList.add('hidden');
        return;
    }
    relatedWrap.classList.remove('hidden');
    relatedList.innerHTML = topics.map(t => `
        <button data-related-topic="${escapeAttr(t)}"
                class="related-chip flat-btn text-xs px-3 py-1.5 border hover:border-purple-500/40"
                style="background: var(--bg-input); border-color: var(--border); color: var(--text-secondary);">
            ${escapeHtml(t)}
        </button>
    `).join('');

    relatedList.querySelectorAll('.related-chip').forEach(btn => {
        btn.addEventListener('click', () => {
            document.getElementById('topic-input').value = btn.dataset.relatedTopic;
            form.requestSubmit();
        });
    });
}

// toggle sidebar visibility
sidebarToggle.addEventListener('click', () => {
    sidebarOpen = !sidebarOpen;
    sidebar.classList.toggle('collapsed', !sidebarOpen);
});

// form submission handler
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const topic = document.getElementById('topic-input').value.trim();
    const expertise = document.getElementById('expertise-select').value;
    const preference = document.getElementById('preference-select').value;
    if (!topic) return;

    renderSkeleton();
    try {
        const raw = await generateCurriculum(topic, expertise, preference);
        currentPath = normalizePath(raw);
        expandedSteps = new Set([0]); // open first step by default
        persistCurrentPath();
        renderCurriculum();
    } catch (err) {
        renderError(err.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.querySelector('span').innerText = 'Generate Path';
    }
});

function renderSkeleton() {
    submitBtn.disabled = true;
    submitBtn.querySelector('span').innerText = 'Generating…';
    outputContainer.innerHTML = `
        <div class="space-y-3">
            <div class="h-20 rounded-2xl border animate-pulse" style="background: var(--bg-panel); border-color: var(--border-soft);"></div>
            <div class="h-20 rounded-2xl border animate-pulse" style="background: var(--bg-panel); border-color: var(--border-soft);"></div>
            <div class="h-20 rounded-2xl border animate-pulse" style="background: var(--bg-panel); border-color: var(--border-soft);"></div>
        </div>
    `;
}

function renderError(message) {
    outputContainer.innerHTML = `
        <div class="rounded-2xl p-5 border space-y-1" style="background: var(--purple-dark); border-color: var(--purple-mid); color: var(--purple-light);">
            <h3 class="font-bold text-sm">Failed to generate path</h3>
            <p class="text-xs opacity-90">${escapeHtml(message)}</p>
        </div>
    `;
}

function updateProgressBar() {
    if (!currentPath || !currentPath.steps.length) {
        progressWrap.classList.add('hidden');
        return;
    }
    const total = currentPath.steps.length;
    const done = currentPath.steps.filter(s => s.status === 'completed').length;
    const percent = Math.round((done / total) * 100);
    progressWrap.classList.remove('hidden');
    progressLabel.textContent = `${done}/${total} steps complete`;
    progressPercent.textContent = `${percent}%`;
    progressFill.style.width = `${percent}%`;
}

function renderCurriculum() {
    if (!currentPath) {
        mutationWrap.classList.add('hidden');
        return;
    }
    mutationWrap.classList.remove('hidden');
    updateProgressBar();
    outputContainer.innerHTML = currentPath.steps.map((step, idx) => renderStepCard(step, idx)).join('');
    attachEventListeners();
    renderRelatedTopics();
}

// handle user prompt mutation submission
mutationForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const promptText = mutationInput.value.trim();
    if (!promptText || !currentPath) return;

    mutationBtn.disabled = true;
    mutationBtn.querySelector('span').innerText = 'Updating…';

    try {
        const data = await mutateCurriculum(currentPath.main_topic, promptText);
        currentPath = normalizePath(data.path);
        persistCurrentPath();
        renderCurriculum();
        mutationInput.value = '';
    } catch (err) {
        alert(err.message);
    } finally {
        mutationBtn.disabled = false;
        mutationBtn.querySelector('span').innerText = 'Modify Path';
    }
});

function renderResourceRow(res, stepIdx, resIdx) {
    const rawUrl = res.url || '';
    const platform = (res.source_platform || '').toLowerCase();
    
    // catch google search fallbacks
    const isGoogleSearch = !rawUrl || 
                           rawUrl === '#' || 
                           rawUrl === 'None' || 
                           rawUrl.includes('google.com/search') || 
                           platform.includes('google');

    const fallbackSearchUrl = `https://www.google.com/search?q=${encodeURIComponent((res.title || '') + ' ' + (currentPath?.main_topic || ''))}`;
    const targetUrl = isGoogleSearch ? fallbackSearchUrl : rawUrl;
    const badgeLabel = isGoogleSearch ? 'TOPIC TO SEARCH' : (res.source_platform || res.resource_type || 'RESOURCE');

    return `
        <div class="resource-row flex items-center gap-3 border px-3 py-2.5" style="background: var(--bg-input); border-color: var(--border-soft);">
            ${!isGoogleSearch ? `
                <span class="check-box ${res.completed ? 'checked' : ''}" data-step-idx="${stepIdx}" data-res-idx="${resIdx}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                        <polyline points="20 6 9 17 4 12"/>
                    </svg>
                </span>
            ` : `
                <!-- fallback search topic icon -->
                <div class="w-[18px] h-[18px] flex-shrink-0 flex items-center justify-center opacity-50">
                    <span class="text-xs">*</span>
                </div>
            `}

            <a href="${targetUrl}" target="_blank" rel="noopener noreferrer" class="flex-1 min-w-0 flex items-center justify-between gap-3 group">
                <div class="min-w-0">
                    <div class="flex items-center gap-2 mb-0.5">
                        <span class="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded border" 
                              style="background: ${isGoogleSearch ? 'var(--blue-dark)' : 'var(--purple-dark)'}; color: ${isGoogleSearch ? 'var(--blue-text)' : 'var(--purple-light)'}; border-color: var(--border);">
                            ${escapeHtml(badgeLabel)}
                        </span>
                        ${res.rating && !isGoogleSearch ? `<span class="text-[11px]" style="color: var(--text-muted);">Rating: ${res.rating}</span>` : ''}
                    </div>
                    <p class="text-sm truncate ${res.completed && !isGoogleSearch ? 'line-through text-slate-500' : ''}" style="color: ${res.completed ? 'var(--text-muted)' : 'var(--text-primary)'};">
                        ${escapeHtml(res.title || 'Search and study topic')}
                    </p>
                </div>
                <span class="text-xs flex-shrink-0 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" style="color: var(--text-muted);">↗</span>
            </a>
        </div>
    `;
}

function renderStepCard(step, index) {
    const isCompleted = step.status === 'completed';
    const isExpanded = expandedSteps.has(index);
    const resources = step.resources || [];
    const doneResources = resources.filter(r => r.completed).length;

    // duration in minutes calculation
    const durationMinutes = step.estimated_minutes 
        ? step.estimated_minutes 
        : (step.estimated_hours ? Math.round(step.estimated_hours * 60) : 30);

    // step type badges
    const stepType = (step.role || step.step_type || 'foundational').toLowerCase();
    const typeBadges = {
        foundational: { label: 'Foundational', bg: '#1f2b4a', text: '#6f97e0', border: '#191d32' },
        deep_dive: { label: 'Deep Dive', bg: '#3b1c4a', text: '#d3a0e8', border: '#1c0d24' },
        practice: { label: 'Practice', bg: '#1c3b2b', text: '#a0e8bc', border: '#103923' },
        reference: { label: 'Reference', bg: '#3b321c', text: '#e8d3a0', border: '#30270e' }
    };
    const badge = typeBadges[stepType] || typeBadges.foundational;

    return `
        <div class="rounded-2xl border overflow-hidden transition-all duration-150 mb-3" style="background: var(--bg-panel); border-color: var(--border);">
            <div class="step-header flex items-start gap-3 p-4 cursor-pointer hover:bg-indigo-950/20" data-step-idx="${index}">
                <svg class="chevron mt-1 flex-shrink-0 ${isExpanded ? 'open' : ''}" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="color: var(--text-muted);">
                    <polyline points="9 18 15 12 9 6"/>
                </svg>

                <div class="flex-1 min-w-0 space-y-1">
                    <div class="flex items-center gap-2 flex-wrap">
                        <span class="text-[11px] font-bold px-2 py-0.5 rounded-md border" style="background: var(--blue-dark); color: var(--blue-text); border-color: var(--border);">
                            Step ${index + 1}
                        </span>

                        <span class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border" 
                              style="background: ${badge.bg}; color: ${badge.text}; border-color: ${badge.border};">
                            ${badge.label}
                        </span>

                        <span class="text-[11px]" style="color: var(--text-muted);">Time expected: ${durationMinutes} min</span>
                        <span class="text-[11px]" style="color: var(--text-muted);">· ${doneResources}/${resources.length} completed</span>
                    </div>

                    <h3 class="text-base font-semibold" style="color: var(--text-primary);">${escapeHtml(step.topic_title || step.title)}</h3>
                </div>

                <button data-step-idx="${index}" class="toggle-status-btn flat-btn flex-shrink-0 px-3 py-1.5 rounded-lg text-[11px] font-semibold border"
                        style="background: ${isCompleted ? 'var(--success-bg)' : 'var(--bg-input)'}; color: ${isCompleted ? 'var(--success-text)' : 'var(--text-secondary)'}; border-color: ${isCompleted ? 'var(--success-border)' : 'var(--border)'};">
                    ${isCompleted ? '✓ Done' : 'Mark complete'}
                </button>
            </div>

            ${isExpanded ? `
                <div class="px-4 pb-4 space-y-3 border-t" style="border-color: var(--border-soft);">
                    ${step.resource_rationale ? `
                        <div class="p-2.5 mt-3 rounded-lg border text-xs" style="background: var(--bg-input); border-color: var(--border-soft); color: var(--purple-light);">
                             <strong>Strategy:</strong> ${escapeHtml(step.resource_rationale)}
                        </div>
                    ` : ''}

                    <div class="space-y-2 pt-2">
                        ${resources.length ? resources.map((res, rIdx) => renderResourceRow(res, index, rIdx)).join('') : `<p class="text-xs italic" style="color: var(--text-muted);">No direct resources for this step.</p>`}
                    </div>
                </div>
            ` : ''}
        </div>
    `;
}

// click handlers
function attachEventListeners() {
    document.querySelectorAll('.step-header').forEach(header => {
        header.addEventListener('click', (e) => {
            if (e.target.closest('.toggle-status-btn')) return;
            const idx = parseInt(header.dataset.stepIdx, 10);
            if (expandedSteps.has(idx)) {
                expandedSteps.delete(idx);
            } else {
                expandedSteps.add(idx);
            }
            renderCurriculum();
        });
    });

    document.querySelectorAll('.toggle-status-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const stepIdx = parseInt(e.currentTarget.dataset.stepIdx, 10);
            const step = currentPath.steps[stepIdx];
            const newStatus = step.status === 'completed' ? 'in_progress' : 'completed';

            try {
                await updateStepProgress(currentPath.main_topic, stepIdx, newStatus);
                step.status = newStatus;
                step.resources = (step.resources || []).map(r => ({ ...r, completed: newStatus === 'completed' }));
                persistCurrentPath();
                renderCurriculum();
            } catch (err) {
                console.error('Failed to sync progress:', err);
            }
        });
    });

    document.querySelectorAll('.check-box').forEach(box => {
        box.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const stepIdx = parseInt(box.dataset.stepIdx, 10);
            const resIdx = parseInt(box.dataset.resIdx, 10);
            const step = currentPath.steps[stepIdx];
            const resource = step.resources[resIdx];
            resource.completed = !resource.completed;

            const allDone = step.resources.length > 0 && step.resources.every(r => r.completed);
            const newStatus = allDone ? 'completed' : 'in_progress';

            if (newStatus !== step.status) {
                try {
                    await updateStepProgress(currentPath.main_topic, stepIdx, newStatus);
                    step.status = newStatus;
                } catch (err) {
                    console.error('Failed to sync step:', err);
                }
            }

            persistCurrentPath();
            renderCurriculum();
        });
    });
}

groqKeyInput.value = getUserGroqKey();
settingsToggle.addEventListener('click', () => settingsPanel.classList.toggle('hidden'));
groqKeySave.addEventListener('click', () => {
    setUserGroqKey(groqKeyInput.value.trim());
    groqKeyStatus.textContent = groqKeyInput.value.trim() ? 'Saved -> using your key now.' : '';
});
groqKeyClear.addEventListener('click', () => {
    groqKeyInput.value = '';
    setUserGroqKey('');
    groqKeyStatus.textContent = 'Cleared -> using default key.';
});

function escapeHtml(str) {
    return String(str ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

function escapeAttr(str) {
    return escapeHtml(str);
}

renderSidebar();
updateProgressBar();