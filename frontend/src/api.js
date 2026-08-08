const API_BASE_URL = "/api/v1";

let activeGroqKey = "";

export function getUserGroqKey() {
    return activeGroqKey;
}

export function setUserGroqKey(key) {
    activeGroqKey = key ? key.trim() : "";
}

export function promptForGroqKey() {
    const key = prompt("Please enter your Groq API Key (It will be saved securely in the database):");
    if (key && key.trim()) {
        setUserGroqKey(key.trim());
        return key.trim();
    }
    return null;
}

// gets response from the generate endpoint
export async function generateCurriculum(topic, expertiseLevel = "intermediate", contentPreference = "balanced", providedKey = null) {
    let userKey = providedKey || getUserGroqKey();

    const makeRequest = async (keyToSend) => {
        return await fetch(`${API_BASE_URL}/curriculum/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                topic: topic,
                expertise_level: expertiseLevel,
                content_preference: contentPreference,
                groq_api_key: keyToSend || null,
            }),
        });
    };

    let response = await makeRequest(userKey);

    // If no key exists in DB (401), prompt user for key and retry once to save it to DB
    if (response.status === 401) {
        userKey = promptForGroqKey();
        if (userKey) {
            response = await makeRequest(userKey);
        }
    }

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
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