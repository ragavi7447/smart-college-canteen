/**
 * Smart College Canteen - Interactive Client Script
 * Handles Cart Operations, Pop-up and Fly-to-Cart Animations, and Notifications
 */

function addToCart(productId, btnElement, event) {
    if (event) {
        event.preventDefault();
    }

    const card = btnElement ? btnElement.closest(".product-card") : document.getElementById("productCard" + productId);
    const productName = card ? (card.querySelector(".product-title")?.innerText || "Item") : "Item";

    // 1. Pop-up effect on the product card itself
    if (card) {
        card.classList.remove("card-popping");
        void card.offsetWidth; // Force reflow
        card.classList.add("card-popping");
        setTimeout(() => card.classList.remove("card-popping"), 360);
    }

    // 2. Flying clone animation (Pops up, then flies into bottom cart)
    triggerFlyToCartAnimation(card, btnElement, productName);

    // 3. Send request to server
    fetch("/add_to_cart/" + productId, {
        method: "POST"
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update cart badges
            updateCartCounts(data.cart_count);
            showToast("✨ " + (data.message || `${productName} added to cart!`), "success");
        } else {
            showToast("⚠️ " + (data.message || "Could not add item."), "warning");
            if (card) {
                card.classList.add("card-shake");
                setTimeout(() => card.classList.remove("card-shake"), 500);
            }
        }
    })
    .catch(error => {
        console.error("Cart error:", error);
        showToast("❌ Unable to connect to server.", "error");
    });
}

/**
 * Creates a floating clone that POPS UP first, then FLIES straight down into the bottom cart
 */
function triggerFlyToCartAnimation(card, btnElement, productName) {
    const targetCart = document.getElementById("bottomCartIcon") || 
                       document.getElementById("bottomCartBtn") || 
                       document.getElementById("headerCartBtn");

    if (!targetCart) return;

    // Get source position (center of card or button)
    let startX = window.innerWidth / 2;
    let startY = window.innerHeight / 2;

    if (card) {
        const rect = card.getBoundingClientRect();
        startX = rect.left + (rect.width / 2) - 45;
        startY = rect.top + 30;
    } else if (btnElement) {
        const rect = btnElement.getBoundingClientRect();
        startX = rect.left + (rect.width / 2) - 45;
        startY = rect.top - 20;
    }

    // Create the flying element
    const flyer = document.createElement("div");
    flyer.className = "flying-item-clone";
    flyer.innerHTML = `<span>🍽️</span> <strong>${escapeHtml(productName)}</strong>`;
    flyer.style.left = `${startX}px`;
    flyer.style.top = `${startY}px`;

    document.body.appendChild(flyer);

    // Step A: Pop up! (scales up, lifts upward with spring)
    requestAnimationFrame(() => {
        flyer.classList.add("pop-up");

        // Step B: Fly down into bottom cart tray
        setTimeout(() => {
            const targetRect = targetCart.getBoundingClientRect();
            const endX = targetRect.left + (targetRect.width / 2) - 25;
            const endY = targetRect.top + (targetRect.height / 2) - 20;

            flyer.classList.remove("pop-up");
            flyer.classList.add("flying-down");
            flyer.style.left = `${endX}px`;
            flyer.style.top = `${endY}px`;

            // Step C: Arrival at cart
            setTimeout(() => {
                flyer.remove();

                // Cart bounce animation
                const bottomBar = document.getElementById("bottomCartBar");
                const bottomIcon = document.getElementById("bottomCartIcon");
                if (bottomIcon) {
                    bottomIcon.classList.remove("cart-bump");
                    void bottomIcon.offsetWidth;
                    bottomIcon.classList.add("cart-bump");
                    setTimeout(() => bottomIcon.classList.remove("cart-bump"), 450);
                }
                if (bottomBar) {
                    bottomBar.classList.add("bar-pulse");
                    setTimeout(() => bottomBar.classList.remove("bar-pulse"), 450);
                }
            }, 550);
        }, 220);
    });
}

/**
 * Updates UI badge counts and bottom summary text
 */
function updateCartCounts(count) {
    if (typeof count === "undefined") return;

    // Bottom cart badge
    const bottomBadge = document.getElementById("bottomCartCountBadge");
    if (bottomBadge) {
        bottomBadge.textContent = count;
        bottomBadge.classList.remove("badge-bump");
        void bottomBadge.offsetWidth;
        bottomBadge.classList.add("badge-bump");
        setTimeout(() => bottomBadge.classList.remove("badge-bump"), 400);
    }

    // Bottom cart subtext
    const subtext = document.getElementById("bottomCartSummaryText");
    if (subtext) {
        subtext.textContent = `${count} item${count === 1 ? '' : 's'} in tray`;
    }

    // Header cart badge
    const headerBadge = document.getElementById("headerCartCount");
    if (headerBadge) {
        headerBadge.textContent = count;
    }
}

/**
 * Non-blocking floating toast notifications
 */
function showToast(message, type = "info") {
    let container = document.getElementById("toastContainer");
    if (!container) {
        container = document.createElement("div");
        container.id = "toastContainer";
        container.className = "toast-container";
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast-pill ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    // Pop in
    requestAnimationFrame(() => {
        toast.classList.add("show");
    });

    // Auto-remove
    setTimeout(() => {
        toast.classList.remove("show");
        setTimeout(() => toast.remove(), 300);
    }, 2200);
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.innerText = text;
    return div.innerHTML;
}