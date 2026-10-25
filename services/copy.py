"""Words the buyer sends from their own WhatsApp (UX spec §1.1: only these use the buyer's voice).

The Hindi avoids gendered verbs: the cook may be Mummy, Papa, Dadi or Nana."""
from urllib.parse import quote

INVITE = {
    "hi": (
        "{who}, हम आपकी रेसिपी की एक किताब बना रहे हैं, आपकी आवाज़ के साथ। "
        "हर पन्ने पर एक QR होगा, जिससे पूरा परिवार आपको बोलते हुए सुन सके।\n\n"
        "पहली रेसिपी: {dish}। जब समय मिले, बस इसे बनाने का तरीका बोलकर मुझे WhatsApp पर "
        "वॉइस नोट भेज दीजिए। अपने अंदाज़ में, जैसे हमेशा बताया है। कोई जल्दी नहीं है।"
    ),
    "hinglish": (
        "{who}, hum aapki recipes ki ek kitaab bana rahe hain, aapki awaaz ke saath. "
        "Har page par ek QR hoga, taaki poori family aapko bolte hue sun sake.\n\n"
        "Pehli recipe: {dish}. Jab time mile, bas ise banane ka tareeka bolkar mujhe WhatsApp par "
        "voice note bhej dijiye. Apne andaaz mein, jaise hamesha bataya hai. Koi jaldi nahi hai."
    ),
    "en": (
        "{who}, we're making a book of your recipes, in your own voice. "
        "Every page will have a QR code so the whole family can hear you tell it.\n\n"
        "First recipe: {dish}. Whenever you have time, just send me a WhatsApp voice note "
        "telling me how you make it, the way you always explain it. There's no hurry."
    ),
}
FIRST_DISH_FALLBACK = {"hi": "आपकी पसंद की कोई भी डिश", "hinglish": "aapki pasand ki koi bhi dish",
                       "en": "any dish you like"}

FAMILY_SHARE = {
    "hi": "हमारी रसोई की किताब: {title}। यहाँ खोलिए और रेसिपी उनकी आवाज़ में सुनिए: {url}",
    "hinglish": "Hamari family cookbook: {title}. Yahan kholiye aur recipes unki awaaz mein suniye: {url}",
    "en": "Our family cookbook: {title}. Open it and hear the recipes in their own voice: {url}",
}


def invite_text(project, first_dish=None):
    language = project.get("storyteller_language") or "hinglish"
    who = project.get("storyteller_address_as") or ("मम्मी" if language == "hi" else "Mummy")
    dish = first_dish or FIRST_DISH_FALLBACK[language]
    return INVITE[language].format(who=who, dish=dish)


def family_share_text(project, url):
    language = project.get("storyteller_language") or "hinglish"
    return FAMILY_SHARE[language].format(title=project["title"], url=url)


def wa_link(text, phone=None):
    """A wa.me link that opens the user's own WhatsApp with `text` ready to send."""
    target = phone.lstrip("+") if phone else ""
    return f"https://wa.me/{target}?text={quote(text)}"


QUESTION = {
    "hi": "{who}, {dish} के बारे में एक बात पूछनी थी: {question}",
    "hinglish": "{who}, {dish} ke baare mein ek baat poochni thi: {question}",
    "en": "{who}, one quick question about the {dish}: {question}",
}


def question_text(project, dish, question):
    """A follow-up question the buyer forwards from their own WhatsApp while the bot is off."""
    language = project.get("storyteller_language") or "hinglish"
    who = project.get("storyteller_address_as") or ("मम्मी" if language == "hi" else "Mummy")
    return QUESTION[language].format(who=who, dish=dish, question=question)


REVEAL = {
    "hi": "{title}: {who} की रसोई की किताब, उनकी अपनी आवाज़ में। हर रेसिपी के साथ उनकी आवाज़ सुनिए: {url}",
    "hinglish": ("{title}: {who} ki recipes ki kitaab, unki apni awaaz mein. "
                 "Har recipe ke saath unki awaaz suniye: {url}"),
    "en": "{title}: {who}'s recipes, in their own voice. Open it and listen to every recipe: {url}",
}


def reveal_text(project, url):
    """The family-group message on reveal day, sent from the buyer's WhatsApp."""
    language = project.get("storyteller_language") or "hinglish"
    who = project.get("storyteller_address_as") or project.get("storyteller_name") or "Mummy"
    return REVEAL[language].format(title=project["title"], who=who, url=url)


NUDGE = {
    "hi": "{who}, जब समय मिले, {dish} बनाने का तरीका एक वॉइस नोट में बता दीजिए। कोई जल्दी नहीं है, "
          "बस आपकी आवाज़ में सुनना अच्छा लगता है।",
    "hinglish": ("{who}, jab time mile, {dish} banane ka tareeka ek voice note mein bata dijiye. "
                 "Koi jaldi nahi hai, bas aapki awaaz mein sunna accha lagta hai."),
    "en": ("{who}, whenever you have a moment, could you tell me how you make {dish} in a voice note? "
           "There's no hurry, it's just lovely to hear it in your voice."),
}


def nudge_text(project, dish=None):
    """A gentle reminder after a quiet stretch (module 11, in-app part), sent from the buyer's WhatsApp."""
    language = project.get("storyteller_language") or "hinglish"
    who = project.get("storyteller_address_as") or ("मम्मी" if language == "hi" else "Mummy")
    return NUDGE[language].format(who=who, dish=dish or FIRST_DISH_FALLBACK[language])
