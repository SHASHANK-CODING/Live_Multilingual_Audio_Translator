import os

# --- Tell MoviePy exactly where to find your bundled ffmpeg.exe ---
ffmpeg_path = os.path.abspath("bin/ffmpeg.exe")

if not os.path.exists(ffmpeg_path):
    raise FileNotFoundError(f"❌ ffmpeg.exe not found at: {ffmpeg_path}")

os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path
print(f"✅ Using bundled ffmpeg from: {ffmpeg_path}")

# --- Now import moviepy ---
import moviepy.editor as mp

# --- Rest of your imports ---
import streamlit as st
import azure.cognitiveservices.speech as speechsdk
import tempfile
import time
import io
import threading
import shutil
import yt_dlp
import concurrent.futures

# =============================================================================
# 1. PAGE CONFIG & SECRETS (Unchanged)
# =============================================================================
st.set_page_config(
    page_title="Azure Media Translator",
    page_icon="🎬",
    layout="wide"
)

try:
    AZURE_KEY = st.secrets["AZURE_KEY"]
    AZURE_LOCATION = st.secrets["AZURE_LOCATION"]
except FileNotFoundError:
    st.error("Please create a .streamlit/secrets.toml file with your Azure credentials.")
    st.stop()
except KeyError:
    st.error("Please add AZURE_KEY and AZURE_LOCATION to your secrets.toml file.")
    st.stop()

# =============================================================================
# 2. LANGUAGE AND VOICE CONFIG (Unchanged)
# =============================================================================
LANG_OPTIONS = {
    'English': 'en-US', 'Hindi': 'hi-IN', 'French': 'fr-FR', 'Spanish': 'es-ES', 'German': 'de-DE',
    'Tamil': 'ta-IN', 'Telugu': 'te-IN', 'Malayalam': 'ml-IN', 'Arabic': 'ar-AE',
    'Chinese (Simplified)': 'zh-CN', 'Russian': 'ru-RU', 'Japanese': 'ja-JP', 'Korean': 'ko-KR'
}
TRANSLATE_OPTIONS = {
    'English': 'en', 'Hindi': 'hi', 'French': 'fr', 'Spanish': 'es', 'German': 'de',
    'Tamil': 'ta', 'Telugu': 'te', 'Malayalam': 'ml', 'Arabic': 'ar', 
    'Chinese (Simplified)': 'zh-cn', 'Russian': 'ru', 'Japanese': 'ja', 'Korean': 'ko'
}
TTS_VOICE_MAP = {
    'en': 'en-US-JennyNeural', 'hi': 'hi-IN-SwaraNeural', 'fr': 'fr-FR-DeniseNeural',
    'es': 'es-ES-ElviraNeural', 'de': 'de-DE-KatjaNeural', 'ta': 'ta-IN-PallaviNeural',
    'te': 'te-IN-ShrutiNeural', 'ml': 'ml-IN-SobhanaNeural', 'ar': 'ar-EG-SalmaNeural',
    'zh-cn': 'zh-CN-XiaoxiaoNeural',
    'ru': 'ru-RU-SvetlanaNeural', 'ja': 'ja-JP-NanamiNeural',
    'ko': 'ko-KR-SunHiNeural'
}

# --- AZURE SDK SETUP ---
@st.cache_resource
def get_azure_configs(source_lang_code, target_voice_name):
    translation_config = speechsdk.translation.SpeechTranslationConfig(
        subscription=AZURE_KEY, 
        region=AZURE_LOCATION
    )
    translation_config.speech_recognition_language = source_lang_code 
    
    synthesis_config = speechsdk.SpeechConfig(
        subscription=AZURE_KEY, 
        region=AZURE_LOCATION
    )
    synthesis_config.speech_synthesis_voice_name = target_voice_name
    return translation_config, synthesis_config

# =============================================================================
# 3. CORE TRANSLATION & HELPER FUNCTIONS (Unchanged)
# =============================================================================

# --- Recognition pipeline ---
def run_recognition_pipeline(audio_file_path, target_lang_code, translation_config):
    translator = None
    audio_input = None
    all_segments = []
    recognized_text_fragments = []
    translated_text_fragments = []

    try:
        audio_input = speechsdk.AudioConfig(filename=audio_file_path)
        translator = speechsdk.translation.TranslationRecognizer(
            translation_config=translation_config,
            audio_config=audio_input
        )
        translator.add_target_language(target_lang_code)
        done = threading.Event()

        def handle_translation(evt):
            if evt.result.reason == speechsdk.ResultReason.TranslatedSpeech:
                start_time_sec = evt.result.offset / 10_000_000
                duration_sec = evt.result.duration / 10_000_000
                original_text = evt.result.text
                translated_text = evt.result.translations[target_lang_code]
                all_segments.append({
                    'start': start_time_sec,
                    'duration': duration_sec,
                    'original': original_text,
                    'translated': translated_text
                })
                recognized_text_fragments.append(original_text)
                translated_text_fragments.append(translated_text)

        def handle_cancellation(evt):
            print(f"❌ CANCELED: {evt.reason} - {evt.error_details}")
            done.set() 

        def handle_session_stopped(evt):
            done.set()

        translator.recognized.connect(handle_translation)
        translator.session_stopped.connect(handle_session_stopped)
        translator.canceled.connect(handle_cancellation)

        translator.start_continuous_recognition_async()
        done.wait() 
        translator.stop_continuous_recognition_async().get()

        full_recognized_text = " ".join(recognized_text_fragments)
        full_translated_text = " ".join(translated_text_fragments)

    except Exception as e:
        print(f"❌ AZURE RECOGNITION FAILED: {e}")
        return None, None, None
        
    finally:
        if translator is not None:
            translator.recognized.disconnect_all()
            translator.session_stopped.disconnect_all()
            translator.canceled.disconnect_all()
            del translator
        if audio_input is not None:
            del audio_input

    return all_segments, full_recognized_text, full_translated_text

# --- Worker function for parallel recognition ---
def recognize_chunk(task_data):
    chunk_path, chunk_index, target_lang_code, translation_config = task_data
    
    segments, rec_text, trans_text = run_recognition_pipeline(
        chunk_path,
        target_lang_code,
        translation_config
    )
    
    return (chunk_index, segments, rec_text, trans_text)

# --- Helper function to split audio ---
def split_audio(audio_path, chunk_duration_sec, temp_dir):
    audio = mp.AudioFileClip(audio_path)
    total_duration = audio.duration
    chunk_paths = []
    
    for i, start_time in enumerate(range(0, int(total_duration) + 1, chunk_duration_sec)):
        end_time = min(start_time + chunk_duration_sec, total_duration)
        if start_time >= end_time:
            continue
            
        chunk_path = os.path.join(temp_dir, f"chunk_{i}.wav")
        
        try:
            sub_audio = audio.subclip(start_time, end_time)
            sub_audio.write_audiofile(
                chunk_path, 
                codec='pcm_s16le', 
                fps=16000, 
                nbytes=2, 
                ffmpeg_params=["-ac", "1"],
                logger=None 
            )
            chunk_paths.append((chunk_path, i, start_time)) 
        except Exception as e:
            st.warning(f"Skipping audio chunk {i} due to split error: {e}")
            
    return chunk_paths


# --- Helper function for parallel synthesis ---
def synthesize_segment(segment_data):
    i, segment, synthesis_config, temp_dir = segment_data
    segment_text = segment['translated']
    segment_start = segment['start']

    if not segment_text or segment_text.isspace():
        return None
    
    segment_audio_path = os.path.join(temp_dir, f"segment_{i}.wav")
    
    try:
        audio_config_tts = speechsdk.audio.AudioOutputConfig(filename=segment_audio_path)
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=synthesis_config,
            audio_config=audio_config_tts
        )
        result_tts = synthesizer.speak_text_async(segment_text).get()

        if result_tts.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            if os.path.exists(segment_audio_path) and os.path.getsize(segment_audio_path) > 44:
                audio_clip = mp.AudioFileClip(segment_audio_path)
                audio_clip = audio_clip.set_start(segment_start)
                return audio_clip
            else:
                return None
        else:
            return None
    except Exception as e:
        print(f"Error in synthesis thread: {e}")
        return None


# =============================================================================
# 4. STREAMLIT UI (Unchanged)
# =============================================================================

# --- Sidebar Controls ---
st.sidebar.header("⚙️ Configuration")
source_lang_name = st.sidebar.selectbox("Translate from (Media's Language):", options=LANG_OPTIONS.keys(), index=0)
source_lang_code = LANG_OPTIONS[source_lang_name]

target_lang_name = st.sidebar.selectbox("Translate to (Output Language):", options=TRANSLATE_OPTIONS.keys(), index=1)
target_lang_code = TRANSLATE_OPTIONS[target_lang_name]
target_voice_name = TTS_VOICE_MAP.get(target_lang_code)

CHUNK_DURATION_SEC = st.sidebar.slider(
    "Processing Chunk Size (seconds)", 
    min_value=30, 
    max_value=120, 
    value=60, 
    step=15,
    help="Smaller chunks = faster parallel processing, but might cut off sentences. Larger chunks = slower, but more accurate context."
)

st.sidebar.info("This app will translate audio from a YouTube video or an uploaded file.")

# --- Main Page Layout ---
st.title("🎬 Azure Media Translator")
st.info(f"Translate media from **{source_lang_name}** to **{target_lang_name}**.")

# =============================================================================
# Temporary Directory Handling (Unchanged)
# =============================================================================
if 'temp_dir' in st.session_state:
    if os.path.exists(st.session_state['temp_dir']):
        try:
            shutil.rmtree(st.session_state['temp_dir'])
        except Exception as e:
            st.warning(f"Could not clean up old temp directory: {e}")

temp_dir = tempfile.mkdtemp()
st.session_state['temp_dir'] = temp_dir
# =============================================================================


# --- Input Selection (Unchanged) ---
input_method = st.radio(
    "Choose media source:", 
    ("YouTube URL", "Upload a File"), 
    horizontal=True
)
video_path = None
audio_only_path = None
uploaded_file = None
url = None
VIDEO_EXTENSIONS = ['mp4', 'mkv', 'avi', 'mov', 'webm']
AUDIO_EXTENSIONS = ['mp3', 'wav', 'm4a', 'ogg', 'flac']

# --- (NEW) Function to write secrets to a file ---
@st.cache_resource
def write_secrets_to_files():
    if 'YOUTUBE_COOKIE_CONTENT' in st.secrets:
        with open('cookies.txt', 'w') as f:
            f.write(st.secrets['YOUTUBE_COOKIE_CONTENT'])
        return True
    return False
write_secrets_to_files()

if input_method == "YouTube URL":
    url = st.text_input("Enter YouTube URL:")
    if url:
        try:
            with st.spinner("Downloading YouTube video... (using yt-dlp)"):
                download_path_template = os.path.join(temp_dir, 'downloaded_video.%(ext)s')
                ydl_opts = {
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'outtmpl': download_path_template,
                    'merge_output_format': 'mp4',
                    'noplaylist': True,
                    'quiet': True,
                    'cookiefile': 'cookies.txt', 
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                final_video_path = os.path.join(temp_dir, 'downloaded_video.mp4')
                if os.path.exists(final_video_path):
                    video_path = final_video_path
                    st.video(video_path)
                else:
                    st.error("Video download failed. The file 'downloaded_video.mp4' was not created.")
                    video_path = None
        except Exception as e:
            st.error(f"Error downloading YouTube video: {e}")
            video_path = None
elif input_method == "Upload a File":
    uploaded_file = st.file_uploader(
        "Choose a video or audio file...", 
        type=VIDEO_EXTENSIONS + AUDIO_EXTENSIONS
    )
    if uploaded_file is not None:
        download_path = os.path.join(temp_dir, uploaded_file.name)
        with open(download_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        _name, ext = os.path.splitext(download_path)
        ext = ext.lower().replace('.', '')
        if ext in VIDEO_EXTENSIONS:
            video_path = download_path
            st.video(video_path)
        elif ext in AUDIO_EXTENSIONS:
            audio_only_path = download_path
            st.audio(audio_only_path)

st.divider()

# =============================================================================
# --- Processing Button (MODIFIED) ---
# =============================================================================
if st.button("Process and Translate", disabled=(video_path is None and audio_only_path is None)):

    translation_config, synthesis_config = get_azure_configs(source_lang_code, target_voice_name)
    temp_audio_path = None
    all_segments = []
    rec_text_fragments = []
    trans_text_fragments = []

    try:
        # ==================================
        #  VIDEO PIPELINE
        # ==================================
        if video_path:
            final_video_path = None
            video_clip = None
            
            # --- STEP 1: Extract Audio ---
            with st.spinner("Step 1/4: Extracting original audio..."):
                video_clip = mp.VideoFileClip(video_path)
                audio_clip = video_clip.audio
                temp_audio_path = os.path.join(temp_dir, "original_audio.wav")
                audio_clip.write_audiofile(
                    temp_audio_path, 
                    codec='pcm_s16le', 
                    fps=16000, 
                    nbytes=2, 
                    ffmpeg_params=["-ac", "1"],
                    logger=None
                )
            st.success("Step 1 (Extraction) complete.")
            
            # --- STEP 2: Split and Recognize in Parallel ---
            with st.spinner(f"Step 2/4: Splitting audio and recognizing chunks in parallel..."):
                chunk_data = split_audio(temp_audio_path, CHUNK_DURATION_SEC, temp_dir)
                tasks = [
                    (chunk_path, idx, target_lang_code, translation_config)
                    for (chunk_path, idx, start_time) in chunk_data
                ]
                results = []
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    results = list(executor.map(recognize_chunk, tasks))
                
                results.sort(key=lambda x: x[0])
                
                for chunk_index, chunk_segments, rec_text, trans_text in results:
                    if chunk_segments:
                        time_offset = chunk_data[chunk_index][2]
                        for segment in chunk_segments:
                            segment['start'] += time_offset
                            all_segments.append(segment)
                        rec_text_fragments.append(rec_text)
                        trans_text_fragments.append(trans_text)
            
            rec_text = " ".join(rec_text_fragments)
            trans_text = " ".join(trans_text_fragments)
            st.success("Step 2 (Recognition) complete.")
            
            # --- STEP 3: Synthesize all segments IN PARALLEL ---
            translated_audio_clips = []
            if all_segments:
                with st.spinner(f"Step 3/4: Synthesizing {len(all_segments)} audio segments in parallel..."):
                    tasks = [
                        (i, segment, synthesis_config, temp_dir) 
                        for i, segment in enumerate(all_segments)
                    ]
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        results = list(executor.map(synthesize_segment, tasks))
                    translated_audio_clips = [clip for clip in results if clip is not None]
                st.success("Step 3 (Synthesis) complete.")
            
            # --- (MODIFIED) STEP 4: Composite Audio and Mux Video ---
            if translated_audio_clips and video_clip:
                with st.spinner("Step 4/4: Building new audio track and mixing video..."):
                    
                    # --- THIS IS THE FIX ---
                    # 1. Create the composite audio clip object
                    final_audio = mp.CompositeAudioClip(translated_audio_clips)
                    final_audio.duration = video_clip.duration
                    
                    # 2. Write it to a single temporary file FIRST
                    final_audio_path = os.path.join(temp_dir, "final_dubbed_audio.wav")
                    final_audio.write_audiofile(
                        final_audio_path, 
                        codec='pcm_s16le', 
                        fps=16000,
                        logger=None
                    )
                    
                    # 3. Load that single file back
                    new_audio_clip = mp.AudioFileClip(final_audio_path)
                    
                    # 4. Set the video's audio to the new single clip
                    final_video_clip = video_clip.set_audio(new_audio_clip)
                    # --- END OF FIX ---

                    final_video_path = os.path.join(temp_dir, "translated_video.mp4")
                    final_video_clip.write_videofile(
                        final_video_path, 
                        codec='libx264', 
                        audio_codec='aac',
                        logger=None
                    )
                st.success("Step 4 (Mixing) complete.")
                st.subheader("Translated Video")
                st.video(final_video_path)
                with open(final_video_path, "rb") as f:
                    st.download_button("Download Translated Video 💾", data=f, file_name="translated_video.mp4")
            
        # ==================================
        #  AUDIO-ONLY PIPELINE (Unchanged)
        # ==================================
        elif audio_only_path:
            # --- STEP 1: Convert Audio ---
            audio_clip_mp = None
            with st.spinner("Step 1/4: Converting original audio..."):
                audio_clip_mp = mp.AudioFileClip(audio_only_path)
                temp_audio_path = os.path.join(temp_dir, "original_audio.wav")
                audio_clip_mp.write_audiofile(
                    temp_audio_path, 
                    codec='pcm_s16le', 
                    fps=16000, 
                    nbytes=2, 
                    ffmpeg_params=["-ac", "1"],
                    logger=None
                )
            st.success("Step 1 (Conversion) complete.") 

            # --- STEP 2: Split and Recognize in Parallel ---
            with st.spinner(f"Step 2/4: Splitting audio and recognizing chunks in parallel..."):
                chunk_data = split_audio(temp_audio_path, CHUNK_DURATION_SEC, temp_dir)
                tasks = [
                    (chunk_path, idx, target_lang_code, translation_config)
                    for (chunk_path, idx, start_time) in chunk_data
                ]
                results = []
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    results = list(executor.map(recognize_chunk, tasks))
                
                results.sort(key=lambda x: x[0])
                
                for chunk_index, chunk_segments, rec_text, trans_text in results:
                    if chunk_segments:
                        time_offset = chunk_data[chunk_index][2]
                        for segment in chunk_segments:
                            segment['start'] += time_offset
                            all_segments.append(segment)
                        rec_text_fragments.append(rec_text)
                        trans_text_fragments.append(trans_text)
            
            rec_text = " ".join(rec_text_fragments)
            trans_text = " ".join(trans_text_fragments)
            st.success("Step 2 (Recognition) complete.")
            
            # --- STEP 3: Synthesize all segments IN PARALLEL ---
            translated_audio_clips = []
            if all_segments:
                with st.spinner(f"Step 3/4: Synthesizing {len(all_segments)} audio segments in parallel..."):
                    tasks = [
                        (i, segment, synthesis_config, temp_dir) 
                        for i, segment in enumerate(all_segments)
                    ]
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        results = list(executor.map(synthesize_segment, tasks))
                    translated_audio_clips = [clip for clip in results if clip is not None]
                st.success("Step 3 (Synthesis) complete.")
            
            # --- STEP 4: Composite Audio and Save ---
            if translated_audio_clips and audio_clip_mp:
                with st.spinner("Step 4/4: Building new dubbed audio track..."):
                    final_audio = mp.CompositeAudioClip(translated_audio_clips)
                    final_audio.duration = audio_clip_mp.duration
                    final_audio_path = os.path.join(temp_dir, "translated_audio.wav")
                    final_audio.write_audiofile(
                        final_audio_path, 
                        codec='pcm_s16le', 
                        fps=16000,
                        logger=None
                    )
                st.success("Step 4 (Mixing) complete.") 
                st.subheader("Translated Audio")
                st.audio(final_audio_path)
                with open(final_audio_path, "rb") as f:
                    st.download_button("Download Translated Audio 💾", data=f, file_name="translated_audio.wav")

        # --- Display Text Results (Common to both) ---
        if rec_text and trans_text:
            st.subheader("Text Results")
            col_res1, col_res2 = st.columns(2)
            with col_res1:
                st.text_area(f"Recognized ({source_lang_name}):", rec_text, height=150)
            with col_res2:
                st.text_area(f"Translated ({target_lang_name}):", trans_text, height=150)
        
        st.success("Total processing complete!")
        
    except Exception as e:
        st.error(f"An error occurred during the processing: {e}")
