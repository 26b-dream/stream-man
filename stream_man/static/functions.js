const htmxFooter = document.querySelector("#htmx-footer-container");
const htmxFooterPadding = document.querySelector("#htmx-footer-padding");

// MutationObserver that will make sure the height of the footer padding always matches the footer's height, this will
// make it so the footer never actually covers up any content on the screen when scrolling to the bottom of the page
const observer = new MutationObserver((mutations) => {
    // Sometimes htmxFooter.clientHeight will return the wrong value because the footer is still being updated, to
    // compensate for this, set a delay of 1/4 a second before changing the size, this should make it where the values
    // properly stay in sync
    setTimeout(() => {
        const height = htmxFooter.clientHeight
        htmxFooterPadding.style.height = `${height}px`;
    }, 250);

});
// Start observing the #htmx-footer element for changes
observer.observe(htmxFooter, { childList: true, subtree: true });


// Implements a double click like function on the clicked element
lastClickedButton = null;
function DoubleClickV2(button_id, url_1_function, url_1_params, url_2_function, url_2_params) {
    // Open first or second URL depending on if the button has been clicked before
    if (lastClickedButton !== button_id) {
        url_1_function(...url_1_params)
        color_card(button_id);
        lastClickedButton = button_id;

    }
    else {
        url_2_function(...url_2_params);
    }
}

function color_card(button_id) {
    // Remove visual selection indicator from all other buttons
    unclick()

    // Add the bg-primary class to the clicked button
    document.querySelector(`#${button_id} div`).classList.add("text-bg-primary");
}

function unclick() {
    // Remove visual selection indicator from all other buttons
    const bgPrimaryElements = document.querySelectorAll(".text-bg-primary");
    bgPrimaryElements.forEach((element) => {
        element.classList.remove("text-bg-primary");
    });
    lastClickedButton = null;
}

// Dynamically change the number of cards per row when the value is updated using the configuration form
function change_cards_per_row(number_of_cards) {
    const cards = document.querySelectorAll("[id^=card]");
    cards.forEach((card) => {
        const cardWidth = 100 / number_of_cards;
        card.style.width = `${cardWidth}%`;
    });
}

// Get a cookie value by name
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}


function move_card_to_top(card_id) {
    const card = document.querySelector(`#${card_id}`);
    card.parentNode.prepend(card);
}

function move_card_to_bottom(card_id) {
    const card = document.querySelector(`#${card_id}`);
    card.parentNode.append(card);
}

function move_card_up(card_id) {
    const card = document.querySelector(`#${card_id}`);
    const previousCard = card.previousElementSibling;
    if (previousCard) {
        card.parentNode.insertBefore(card, previousCard);
    }
}

function move_card_down(card_id) {
    const card = document.querySelector(`#${card_id}`);
    const nextCard = card.nextElementSibling;
    if (nextCard) {
        card.parentNode.insertBefore(nextCard, card);
    }
}

function click_next_card(card_id) {
    const card = document.querySelector(`#${card_id}`);
    const nextCard = card.nextElementSibling;
    if (nextCard) {
        const innerDiv = nextCard.querySelector("div");
        innerDiv.click();
    }
}

function click_prev_card(card_id) {
    const card = document.querySelector(`#${card_id}`);
    const prevCard = card.previousElementSibling;
    if (prevCard) {
        const innerDiv = prevCard.querySelector("div");
        innerDiv.click();
    }
}


// Special function for the playlist view
// When the filter episode form is submitted it will update the hx-vals of the target element that is refreshed when the
// form is submitted then submit the form. This will make the episode list automatically refresh to match the form that
// was submitted
function set_playlist_episode_refresh_filter_values(form_id) {
    // get data from the form
    const formData = new FormData(document.querySelector(`#${form_id}`));
    // Convert it into a more usable object that can be made into JSON
    const object = Object.fromEntries(formData);

    const json_string = JSON.stringify(object)

    // Update the value
    console.log("EXECUTED")
    document.querySelector("#playlist-cards").setAttribute("hx-vals", json_string);
    document.querySelector("#open-filter-episodes-form-button").setAttribute("hx-vals", json_string);
}

function get_playlist_id_from_url() {
    const url = window.location.href;
    const url_parts = url.split("/");
    const playlist_id = url_parts[url_parts.length - 1];
    return playlist_id;
}

var playlist_id = get_playlist_id_from_url()
