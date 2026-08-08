const API_BASE_URL = "/api/v1";
const GROQ_KEY_STORAGE = "lumina_user_groq_key";

export function getUserGroqKey() {
    return localStorage.getItem(GROQ_KEY_STORAGE) || "";
}

export function setUserGroqKey(key) {
    if (key && key.trim()) {
        localStorage.setItem(GROQ_KEY_STORAGE, key.trim());
    } else {
        localStorage.removeItem(GROQ_KEY_STORAGE);
    }
}

export function promptForGroqKey() {
    let key = getUserGroqKey();
    if (!key) {
        key = prompt("Please enter your Groq API Key to proceed (You can get one free from https://console.groq.com/keys):");
        if (key && key.trim()) {
            setUserGroqKey(key.trim());
            return key.trim();
        }
    }
    return key;
}

// gets response from the generate endpoint
export async function generateCurriculum(topic, expertiseLevel = "intermediate", contentPreference = "balanced") {
    // prompt user if key isn't stored in localstorage yet
    const userKey = promptForGroqKey();

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
        const errorData = await response.json().catch(() => ({}));
        // clear invalid api key from storage on auth failure
        if (response.status === 401 || response.status === 403) {
            setUserGroqKey(null);
        }
        
        throw new Error(errorData.detail || "Failed to generate curriculum.");
    }

    return await response.json();
}

// updates completion status of a step
export async function updateStepProgress(topic, stepIndex, status) {
    const response = await fetch(`${API_BASE_URL}/curriculum/${encodeURIComponent(topic)}/progress`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step_index: stepIndex, status: status }),
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to update step progress.");
    }

    return await response.json();
}

// sends user natural language prompt to mutate active path
export async function mutateCurriculum(topic, message) {
    const response = await fetch(`${API_BASE_URL}/curriculum/mutate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, message }),
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to update path with prompt.");
    }

    return await response.json();
}