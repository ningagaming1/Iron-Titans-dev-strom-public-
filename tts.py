"""
text_to_speech.py
------------------
A drop-in Text-to-Speech (TTS) module designed to plug into a voice pipeline
that already has a Speech-to-Text (STT) module.

Pipeline this fits into:

    [Mic Input] -> [STT module] -> text -> [Website displays text]
                                          -> [THIS MODULE: TTS] -> user hears it back
                                          -> (if user confirms) -> [Backend]

Two engines are supported:
    1. OFFLINE  -> pyttsx3   (no internet needed, works instantly, robotic-ish voice)
    2. ONLINE   -> gTTS      (needs internet, Google's voice, sounds more natural)

Both are wrapped behind the SAME interface (TextToSpeech class) so you can
swap engines without changing the rest of your code.
"""

import os
import io
import tempfile


class TextToSpeech:
    def __init__(self, engine="offline", rate=150, volume=1.0, voice_lang="en"):
        """
        engine     : "offline" (pyttsx3) or "online" (gTTS)
        rate       : speaking speed (offline engine only)
        volume     : 0.0 to 1.0 (offline engine only)
        voice_lang : language code, e.g. "en", "hi" (used by both, mainly online)
        """
        self.engine_type = engine
        self.voice_lang = voice_lang

        if self.engine_type == "offline":
            import pyttsx3
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", rate)
            self.engine.setProperty("volume", volume)
        elif self.engine_type == "online":
            from gtts import gTTS
            self.gTTS = gTTS
        else:
            raise ValueError("engine must be 'offline' or 'online'")

    # ---------- CORE METHOD 1: Speak immediately (rehear on the spot) ----------
    def speak(self, text: str):
        """
        Converts text to speech and plays it immediately through the speakers.
        Use this for the 'let the user hear what they said' step.
        """
        if not text or not text.strip():
            raise ValueError("No text provided to speak.")

        if self.engine_type == "offline":
            self.engine.say(text)
            self.engine.runAndWait()
        else:
            # online engine: generate to a temp file, then play it
            path = self.save(text)
            self._play_audio_file(path)
            os.remove(path)

    # ---------- CORE METHOD 2: Save to a file (to send to backend / STT format) ----------
    def save(self, text: str, filename: str = None) -> str:
        """
        Converts text to speech and saves it as an audio file.
        Returns the file path, so it can be attached to a backend request
        or fed back into your STT module for testing.

        filename: if you don't give one, a temp .mp3/.wav is created for you.
        """
        if not text or not text.strip():
            raise ValueError("No text provided to save.")

        if self.engine_type == "offline":
            filename = filename or self._temp_path(".wav")
            self.engine.save_to_file(text, filename)
            self.engine.runAndWait()
        else:
            filename = filename or self._temp_path(".mp3")
            tts = self.gTTS(text=text, lang=self.voice_lang)
            tts.save(filename)

        return filename

    # ---------- Helper: play any audio file (used internally by online engine) ----------
    def _play_audio_file(self, path: str):
        from playsound import playsound
        playsound(path)

    def _temp_path(self, ext: str) -> str:
        fd, path = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        return path


# ---------------------------------------------------------------------------
# EXAMPLE: how this plugs into your existing STT -> website -> backend flow
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # -----------------------------------------------------------------
    # RIGHT NOW (testing, STT not ready): just hardcode text like this ↓
    recognized_text = "This is the text that came from the speech to text module."

    # LATER (once your STT file is ready): delete the line above and
    # import + call your real STT function instead, e.g.:
    #
    #   from your_stt_file import transcribe_audio
    #   recognized_text = transcribe_audio(audio_input)
    #
    # Whatever your STT function returns (a plain string), just assign
    # it to `recognized_text` here — nothing else in this file changes.
    # -----------------------------------------------------------------

    tts = TextToSpeech(engine="offline")   # switch to "online" if you want gTTS

    # Step 1: Let the user REHEAR what was recognized
    tts.speak(recognized_text)

    # Step 2: Save the confirmed text as audio too, in case the backend
    # expects an audio file (not just raw text) alongside the transcript
    audio_path = tts.save(recognized_text, filename="confirmed_output.wav")
    print(f"Saved audio for backend at: {audio_path}")

    # Step 3: Now send `recognized_text` (and/or `audio_path`) to your backend
    # e.g. requests.post(url, json={"text": recognized_text})
    # or   requests.post(url, files={"audio": open(audio_path, "rb")})