/* app.js: Frontend logic for ExplainDeFi API */

document.addEventListener("DOMContentLoaded", () => {

    // UI Elements
    const inputField = document.getElementById("tx-input");
    const diagnoseBtn = document.getElementById("diagnose-btn");
    const errorMsg = document.getElementById("error-msg");
    const btnText = document.querySelector(".btn-text");
    const spinner = document.querySelector(".spinner");

    const loadingState = document.getElementById("loading-state");
    const resultsState = document.getElementById("results-state");

    // Result DOM mapping
    const resBadge = document.getElementById("res-badge");
    const resConfidence = document.getElementById("res-confidence");
    const resFunction = document.getElementById("res-function");
    const resContract = document.getElementById("res-contract");
    const resError = document.getElementById("res-error");
    const resGas = document.getElementById("res-gas");
    const resValue = document.getElementById("res-value");
    const resExplanation = document.getElementById("res-explanation");
    const resFixSteps = document.getElementById("res-fix-steps");
    const resTech = document.getElementById("res-tech");
    const resProvider = document.getElementById("res-provider");

    // Accordion Toggle
    const techBtn = document.getElementById("tech-btn");
    const techContent = document.getElementById("tech-content");

    techBtn.addEventListener("click", () => {
        techBtn.classList.toggle("expanded");
        if (techContent.style.maxHeight) {
            techContent.style.maxHeight = null;
        } else {
            techContent.style.maxHeight = techContent.scrollHeight + "px";
        }
    });

    // Handle Diagnose click
    diagnoseBtn.addEventListener("click", handleDiagnose);
    inputField.addEventListener("keypress", (e) => {
        if (e.key === "Enter") handleDiagnose();
    });

    async function handleDiagnose() {
        const txHash = inputField.value.trim().toLowerCase();

        // Basic validation
        if (!txHash.startsWith("0x") || txHash.length !== 66) {
            showError("Please enter a valid Ethereum transaction hash (0x... 64 chars)");
            return;
        }

        // Reset UI
        showError("");
        setLoading(true);
        resultsState.classList.add("hidden");

        // Cycle loading messages for UX
        startLoadingAnimation();

        try {
            // Call FastAPI backend
            // Because we serve the index.html via FastAPI, we can use relative /api/diagnose path
            const response = await fetch("/api/diagnose", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tx_hash: txHash })
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || "Server error occurred");
            }

            const data = await response.json();

            if (data.success && data.report) {
                renderResults(data.report);
            } else {
                throw new Error("Invalid response from server");
            }

        } catch (error) {
            showError(error.message);
            resultsState.classList.add("hidden");
        } finally {
            setLoading(false);
            stopLoadingAnimation();
        }
    }

    function renderResults(report) {

        // Safety checks
        const diag = report.diagnosis || {};
        const expl = report.explanation || {};
        const tx = report.tx_data || {};
        const ctx = report.contract_context || {};

        // 1. Badge & confidence
        if (diag.category === "NONE" || diag.sub_type === "SUCCESS") {
            resBadge.textContent = "SUCCESS / CONFIRMED";
            resBadge.className = "category-badge none";
            resultsState.classList.add("success");
            document.querySelector(".explanation-box .icon").textContent = "🎉";
            document.querySelector(".fix-box .icon").textContent = "✅";
        } else {
            resBadge.textContent = `${diag.category} / ${diag.sub_type}`;
            resBadge.className = `category-badge ${diag.category.toLowerCase()}`;
            resultsState.classList.remove("success");
            document.querySelector(".explanation-box .icon").textContent = "🤖";
            document.querySelector(".fix-box .icon").textContent = "💡";
        }
        resConfidence.style.width = `${(expl.confidence || diag.confidence || 0) * 100}%`;

        // 2. Tx Meta
        resFunction.textContent = ctx.function_name || tx.function_name || "Unknown fallback";
        resError.textContent = diag.raw_error || (diag.category === "NONE" ? "Transaction Succeeded" : "No revert reason provided");
        resError.style.color = diag.category === "NONE" ? "var(--green-success)" : "var(--red-alert)";

        const gasUsedClean = tx.gas_used ? tx.gas_used.toLocaleString() : "0";
        const gasLimitClean = tx.gas_limit ? tx.gas_limit.toLocaleString() : "0";
        resGas.textContent = `${gasUsedClean} / ${gasLimitClean}`;

        const ethValue = tx.value ? (parseInt(tx.value) / 1e18).toFixed(4) : "0.00";
        resValue.textContent = `${ethValue} ETH`;

        // 3. Explanation
        resExplanation.textContent = expl.explanation || diag.description || "Unknown error";

        // 4. Fix Steps
        resFixSteps.innerHTML = "";
        const steps = expl.fix_steps || [];
        if (steps.length > 0) {
            steps.forEach(step => {
                const li = document.createElement("li");
                li.textContent = step;
                resFixSteps.appendChild(li);
            });
        } else {
            const li = document.createElement("li");
            li.textContent = "No fix steps available.";
            resFixSteps.appendChild(li);
        }

        // 5. Technical (Accordion)
        resTech.textContent = expl.technical_summary || "No technical details provided.";
        resProvider.textContent = expl.llm_provider || "System";

        // Show Results Panel
        resultsState.classList.remove("hidden");
    }

    function showError(msg) {
        errorMsg.textContent = msg;
        if (msg) {
            errorMsg.classList.add("visible");
            inputField.style.borderColor = "var(--red-alert)";
        } else {
            errorMsg.classList.remove("visible");
            inputField.style.borderColor = "var(--card-border)";
        }
    }

    function setLoading(isLoading) {
        if (isLoading) {
            diagnoseBtn.disabled = true;
            btnText.classList.add("hidden");
            spinner.classList.remove("hidden");
            loadingState.classList.remove("hidden");
        } else {
            diagnoseBtn.disabled = false;
            btnText.classList.remove("hidden");
            spinner.classList.add("hidden");
            loadingState.classList.add("hidden");
        }
    }

    // UX Animation logic
    let loaderInterval;
    function startLoadingAnimation() {
        const steps = document.querySelectorAll(".step");
        let currentStep = 0;

        steps.forEach(s => s.classList.remove("active"));
        steps[0].classList.add("active");

        loaderInterval = setInterval(() => {
            currentStep++;
            if (currentStep < steps.length) {
                steps.forEach(s => s.classList.remove("active"));
                steps[currentStep].classList.add("active");
            } else {
                clearInterval(loaderInterval);
            }
        }, 3000); // Progress every 3 secs
    }

    function stopLoadingAnimation() {
        clearInterval(loaderInterval);
    }
});
