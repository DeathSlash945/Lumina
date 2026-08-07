const API_BASE_URL = "http://localhost:8000/api/v1";
const GROQ_KEY_STORAGE = "lumina_user_groq_key";

export function getUserGroqKey() {
    return localStorage.getItem(GROQ_KEY_STORAGE) || "";
}

export function setUserGroqKey(key) {
    if (key) localStorage.setItem(GROQ_KEY_STORAGE, key);
    else localStorage.removeItem(GROQ_KEY_STORAGE);
}

export async function generateCurriculum(topic, expertiseLevel = "intermediate", contentPreference = "balanced") {
    const userKey = getUserGroqKey();

    const response = await fetch(`${API_BASE_URL}/curriculum/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            topic: topic,
            expertise_level: expertiseLevel,
            content_preference: contentPreference,
            groq_api_key: userKey || null,
        }),
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to generate curriculum.");
    }

    return await response.json();
}

export async function updateStepProgress(topic, stepIndex, status) {
    const response = await fetch(`${API_BASE_URL}/curriculum/${encodeURIComponent(topic)}/progress`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step_index: stepIndex, status: status }),
    });

    if (!response.ok) {
        throw new Error("Failed to update step progress.");
    }

    return await response.json();
}