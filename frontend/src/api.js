const API_BASE_URL = "/api/v1";

export async function saveGroqKeyToDB(key) {
    const res = await fetch(`${API_BASE_URL}/config/groq-key`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ groq_api_key: key }),
    });

    if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to save API key to database.");
    }
    return await res.json();
}

export async function clearGroqKeyFromDB() {
    const res = await fetch(`${API_BASE_URL}/config/groq-key`, {
        method: "DELETE",
    });

    if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to clear API key.");
    }
    return await res.json();
}

export async function getGroqKeyStatus() {
    const res = await fetch(`${API_BASE_URL}/config/groq-key`);
    if (!res.ok) {
        return { has_key: false };
    }
    return await res.json();
}

export async function generateCurriculum(topic, expertiseLevel = "intermediate", contentPreference = "balanced") {
    let response;

    try {
        response = await fetch(`${API_BASE_URL}/curriculum/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                topic: topic,
                expertise_level: expertiseLevel,
                content_preference: contentPreference,
            }),
        });
    } catch (err) {
        throw new Error("Unable to connect to the backend server. Make sure Docker is running.");
    }

    // Handle 401 Unauthorized (No valid API key found in DB)
    if (response.status === 401) {
        const key = prompt("Please enter your Groq API Key (It will be saved securely in the database):");
        if (key && key.trim()) {
            await saveGroqKeyToDB(key.trim());
            // Retry request once saved to DB
            return generateCurriculum(topic, expertiseLevel, contentPreference);
        } else {
            throw new Error("A valid Groq API Key is required to generate a path.");
        }
    }

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
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
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to update step progress.");
    }

    return await response.json();
}

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