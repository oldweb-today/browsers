import os


# Determine which audio format to stream, depending on
# 1. client request, ex: init_browser?audio=mp3|opus
# 2. supported audio format by virtual browser  (using Docker's labels)
# 3. Authorized media in the stack (defined by environment variables)
def determine_audio_type(requested_formats, browser_info):

    authorized_formats = os.environ.get("AUDIO_TYPE").split("|")
    requested_formats = requested_formats.split("|")
    browser_tags = extract_browser_audio_labels(browser_info)

    for audio in requested_formats:
        if browser_tags is None:
            if audio in authorized_formats:
                return audio
        else:
            if audio in browser_tags:
                if audio in authorized_formats:
                    return audio


# extract supported audio format in the docker browser (if available)
def extract_browser_audio_labels(browser_info):
    if "caps.audio" in browser_info:
        return browser_info["caps.audio"].split("|")


# copy environment variables to the container
def get_audio_env(audio):
    audio_env = {}
    for name in os.environ:
        if name.startswith("AUDIO"):
            audio_env[name] = os.environ.get(name)
        if audio is not None and name.startswith(audio.upper()):
            audio_env[name] = os.environ.get(name)
    return audio_env
