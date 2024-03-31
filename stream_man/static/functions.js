"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
// Autoamtic compiler command: tsc -w functions.ts -target es2022 --moduleResolution nodenext --module nodenext
function setCardColumns(columns) {
    const cards = document.querySelectorAll("[id^=card]");
    cards.forEach((card) => {
        card.style.width = `${100 / columns}%`;
    });
}
function setImageWidth(width) {
    const images = document.querySelectorAll(".card-img-top");
    images.forEach((image) => {
        // Take existing url and replace the last number with the width
        const url = image.getAttribute("src");
        const url_parts = url?.split("/");
        if (url_parts != null) {
            url_parts[url_parts.length - 1] = width.toString();
            image.setAttribute("src", url_parts.join("/"));
        }
    });
}
function saveVisualConfig(playlist_id) {
    const columns = document.querySelector("#visual-config-form-columns");
    document.cookie = `playlist-${playlist_id}-columns=${columns.value}; path=/`;
    const imageWidth = document.querySelector("#visual-config-form-image-width");
    document.cookie = `playlist-${playlist_id}-image-width=${imageWidth.value}; path=/`;
}
function getCookie(name, defaultValue) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        const popped = parts.pop();
        return String(popped?.split(';')?.shift());
    }
    return defaultValue.toString();
}
// MutationObserver that will make sure the height of the footer padding always matches the footer's height, this will
// make it so the footer never actually covers up any content on the screen when scrolling to the bottom of the page
// TODO: This can probably be activated using htmx instead of a MutationObserver since every footer is called through htmx
const htmxFooter = document.querySelector("#htmx-footer-container");
const htmxFooterPadding = document.querySelector("#htmx-footer-padding");
if (htmxFooter != null && htmxFooterPadding != null) {
    const observer = new MutationObserver((mutations) => {
        // Sometimes htmxFooter.clientHeight will return the wrong value because the footer is still being updated, to
        // compensate for this, set a delay of 1/4 a second before changing the size, this should make it where the values
        // properly stay in sync without being noticable.
        setTimeout(() => {
            const height = htmxFooter.clientHeight;
            htmxFooterPadding.style.height = `${height}px`;
        }, 250);
    });
    // Start observing the #htmx-footer element for changes
    observer.observe(htmxFooter, { childList: true, subtree: true });
}
function highlightCard(card_id) {
    const cards = document.querySelectorAll("[id^=actual-card-]");
    cards.forEach((card) => {
        card.classList.remove("bg-primary");
    });
    const card = document.querySelector(`#actual-card-${card_id}`);
    card?.classList?.add("bg-primary");
}
function moveCardToTop(card_id) {
    const card = document.querySelector(`#card-${card_id}`);
    card?.parentNode?.prepend(card);
}
function moveCardToBottom(card_id) {
    const card = document.querySelector(`#card-${card_id}`);
    card?.parentNode?.append(card);
}
function moveCardUp(card_id) {
    const card = document.querySelector(`#card-${card_id}`);
    const previousCard = card?.previousElementSibling;
    if (previousCard) {
        card?.parentNode?.insertBefore(card, previousCard);
    }
}
function moveCardDown(card_id) {
    const card = document.querySelector(`#card-${card_id}`);
    const nextCard = card?.nextElementSibling;
    if (nextCard) {
        card?.parentNode?.insertBefore(nextCard, card);
    }
}
function clickNextCard(card_id) {
    const card = document.querySelector(`#card-${card_id}`);
    card?.nextElementSibling?.querySelector("div")?.click();
}
function clickPrevCard(card_id) {
    const card = document.querySelector(`#card-${card_id}`);
    const prevCard = card?.previousElementSibling?.querySelector("div")?.click();
}
