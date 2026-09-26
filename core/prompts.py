import json
from core.utils import *


def _format_video_style_section(video_style):
    style = str(video_style or "").strip()
    if not style:
        return ""
    return f"""

### User Video Context / Style Guidance
{style}"""


## ================================================================
# @ step4_splitbymeaning.py
def get_split_prompt(sentence, num_parts = 2, word_limit = 20):
    language = load_key("whisper.detected_language")
    split_prompt = f"""
## Role
You are a professional Netflix subtitle splitter in **{language}**.

## Task
Split the given subtitle text into **{num_parts}** parts, each less than **{word_limit}** words.

1. Maintain sentence meaning coherence according to Netflix subtitle standards
2. MOST IMPORTANT: Keep parts roughly equal in length (minimum 3 words each)
3. Split at natural points like punctuation marks or conjunctions
4. If provided text is repeated words, simply split at the middle of the repeated words.

## Steps
1. Analyze the sentence structure, complexity, and key splitting challenges
2. Generate two alternative splitting approaches with [br] tags at split positions
3. Compare both approaches highlighting their strengths and weaknesses
4. Choose the best splitting approach

## Given Text
<split_this_sentence>
{sentence}
</split_this_sentence>

## Output in only JSON format and no other text
```json
{{
    "analysis": "Brief description of sentence structure, complexity, and key splitting challenges",
    "split1": "First splitting approach with [br] tags at split positions",
    "split2": "Alternative splitting approach with [br] tags at split positions",
    "assess": "Comparison of both approaches highlighting their strengths and weaknesses",
    "choice": "1 or 2"
}}
```

Note: Start you answer with ```json and end with ```, do not add any other text.
""".strip()
    return split_prompt

"""{{
    "analysis": "Brief analysis of the text structure",
    "split": "Complete sentence with [br] tags at split positions"
}}"""

## ================================================================
# @ step4_1_summarize.py
def get_summary_prompt(source_content, custom_terms_json=None, video_style=None):
    src_lang = load_key("whisper.detected_language")
    tgt_lang = load_key("target_language")
    
    # add custom terms note
    terms_note = ""
    if custom_terms_json:
        terms_list = []
        for term in custom_terms_json['terms']:
            terms_list.append(f"- {term['src']}: {term['tgt']} ({term['note']})")
        terms_note = "\n### Existing Terms\nPlease exclude these terms in your extraction:\n" + "\n".join(terms_list)
    
    style_note = _format_video_style_section(video_style)

    summary_prompt = f"""
## Role
You are a video translation expert and terminology consultant, specializing in {src_lang} comprehension and {tgt_lang} expression optimization.

## Task
For the provided {src_lang} video text:
1. Summarize main topic in two sentences
2. Extract professional terms/names with {tgt_lang} translations (excluding existing terms)
3. Provide brief explanation for each term

{terms_note}{style_note}

Steps:
1. Topic Summary:
   - Quick scan for general understanding
   - Write two sentences: first for main topic, second for key point
2. Term Extraction:
   - Mark professional terms and names (excluding those listed in Existing Terms)
   - Provide {tgt_lang} translation or keep original
   - Add brief explanation
   - Extract less than 15 terms

## INPUT
<text>
{source_content}
</text>

## Output in only JSON format and no other text
{{
  "theme": "Two-sentence video summary",
  "terms": [
    {{
      "src": "{src_lang} term",
      "tgt": "{tgt_lang} translation or original", 
      "note": "Brief explanation"
    }},
    ...
  ]
}}  

## Example
{{
  "theme": "本视频介绍人工智能在医疗领域的应用现状。重点展示了AI在医学影像诊断和药物研发中的突破性进展。",
  "terms": [
    {{
      "src": "Machine Learning",
      "tgt": "机器学习",
      "note": "AI的核心技术，通过数据训练实现智能决策"
    }},
    {{
      "src": "CNN",
      "tgt": "CNN",
      "note": "卷积神经网络，用于医学图像识别的深度学习模型"
    }}
  ]
}}

Note: Start you answer with ```json and end with ```, do not add any other text.
""".strip()
    return summary_prompt

## ================================================================
# @ step5_translate.py & translate_lines.py
def generate_shared_prompt(previous_content_prompt, after_content_prompt, summary_prompt, things_to_note_prompt, video_style=None):
    shared_prompt = f'''### Context Information
<previous_content>
{previous_content_prompt}
</previous_content>

<subsequent_content>
{after_content_prompt}
</subsequent_content>

### Content Summary
{summary_prompt}

### Points to Note
{things_to_note_prompt}'''
    return shared_prompt + _format_video_style_section(video_style)

def get_prompt_faithfulness(lines, shared_prompt, item_ids=None):
    TARGET_LANGUAGE = load_key("target_language")
    # Split lines by \n
    line_splits = lines.split('\n')
    ids = [str(i) for i in range(1, len(line_splits) + 1)] if item_ids is None else [str(item_id) for item_id in item_ids]
    if len(ids) != len(line_splits):
        raise ValueError("item_ids must match the number of subtitle lines")
    
    json_dict = {}
    for position, (item_id, line) in enumerate(zip(ids, line_splits), start=1):
        placeholder = (
            f"direct {TARGET_LANGUAGE} translation {position}."
            if item_ids is None
            else f"direct {TARGET_LANGUAGE} translation for {item_id}."
        )
        json_dict[item_id] = {"origin": line, "direct": placeholder}
    json_format = json.dumps(json_dict, indent=2, ensure_ascii=False)
    subtitles_input = (
        lines
        if item_ids is None
        else json.dumps(
            [{"id": item_id, "text": line} for item_id, line in zip(ids, line_splits)],
            indent=2,
            ensure_ascii=False,
        )
    )

    src_language = load_key("whisper.detected_language")
    prompt_faithfulness = f'''
## Role
You are a professional Netflix subtitle translator, fluent in both {src_language} and {TARGET_LANGUAGE}, as well as their respective cultures. 
Your expertise lies in accurately understanding the semantics and structure of the original {src_language} text and faithfully translating it into {TARGET_LANGUAGE} while preserving the original meaning.

## Task
We have a segment of original {src_language} subtitles that need to be directly translated into {TARGET_LANGUAGE}. These subtitles come from a specific context and may contain specific themes and terminology.

1. Translate the original {src_language} subtitles into {TARGET_LANGUAGE} line by line
2. Ensure the translation is faithful to the original, accurately conveying the original meaning
3. Consider the context and professional terminology

{shared_prompt}

<translation_principles>
1. Faithful to the original: Accurately convey the content and meaning of the original text, without arbitrarily changing, adding, or omitting content.
2. Accurate terminology: Use professional terms correctly and maintain consistency in terminology.
3. Understand the context: Fully comprehend and reflect the background and contextual relationships of the text.
</translation_principles>

## INPUT
<subtitles>
{subtitles_input}
</subtitles>

## Output in only JSON format and no other text
```json
{json_format}
```

Note: Start you answer with ```json and end with ```, do not add any other text.
'''
    return prompt_faithfulness.strip()


def get_prompt_expressiveness(faithfulness_result, lines, shared_prompt, item_ids=None):
    TARGET_LANGUAGE = load_key("target_language")
    ids = list(faithfulness_result) if item_ids is None else [str(item_id) for item_id in item_ids]
    json_format = {
        key: {
            "origin": faithfulness_result[key]["origin"],
            "direct": faithfulness_result[key]["direct"],
            "reflect": "your reflection on direct translation",
            "free": "your free translation"
        }
        for key in ids
    }
    json_format = json.dumps(json_format, indent=2, ensure_ascii=False)
    line_splits = lines.split('\n')
    subtitles_input = (
        lines
        if item_ids is None
        else json.dumps(
            [{"id": item_id, "text": line} for item_id, line in zip(ids, line_splits)],
            indent=2,
            ensure_ascii=False,
        )
    )

    src_language = load_key("whisper.detected_language")
    prompt_expressiveness = f'''
## Role
You are a professional Netflix subtitle translator and language consultant.
Your expertise lies not only in accurately understanding the original {src_language} but also in optimizing the {TARGET_LANGUAGE} translation to better suit the target language's expression habits and cultural background.

## Task
We already have a direct translation version of the original {src_language} subtitles.
Your task is to reflect on and improve these direct translations to create more natural and fluent {TARGET_LANGUAGE} subtitles.

1. Analyze the direct translation results line by line, pointing out existing issues
2. Provide detailed modification suggestions
3. Perform free translation based on your analysis
4. Do not add comments or explanations in the translation, as the subtitles are for the audience to read
5. Do not leave empty lines in the free translation, as the subtitles are for the audience to read

{shared_prompt}

<Translation Analysis Steps>
Please use a two-step thinking process to handle the text line by line:

1. Direct Translation Reflection:
   - Evaluate language fluency
   - Check if the language style is consistent with the original text
   - Check the conciseness of the subtitles, point out where the translation is too wordy

2. {TARGET_LANGUAGE} Free Translation:
   - Aim for contextual smoothness and naturalness, conforming to {TARGET_LANGUAGE} expression habits
   - Ensure it's easy for {TARGET_LANGUAGE} audience to understand and accept
   - Adapt the language style to match the theme (e.g., use casual language for tutorials, professional terminology for technical content, formal language for documentaries)
</Translation Analysis Steps>
   
## INPUT
<subtitles>
{subtitles_input}
</subtitles>

## Output in only JSON format and no other text
```json
{json_format}
```

Note: Start you answer with ```json and end with ```, do not add any other text.
'''
    return prompt_expressiveness.strip()


## ================================================================
# @ step6_splitforsub.py
def get_align_prompt(src_sub, tr_sub, src_part):
    targ_lang = load_key("target_language")
    src_lang = load_key("whisper.detected_language")
    src_splits = src_part.split('\n')
    num_parts = len(src_splits)
    src_part = src_part.replace('\n', ' [br] ')
    align_parts_json = ','.join(
        f'''
        {{
            "src_part_{i+1}": "{src_splits[i]}",
            "target_part_{i+1}": "Corresponding aligned {targ_lang} subtitle part"
        }}''' for i in range(num_parts)
    )

    align_prompt = f'''
## Role
You are a Netflix subtitle alignment expert fluent in both {src_lang} and {targ_lang}.

## Task
We have {src_lang} and {targ_lang} original subtitles for a Netflix program, as well as a pre-processed split version of {src_lang} subtitles.
Your task is to create the best splitting scheme for the {targ_lang} subtitles based on this information.

1. Analyze the word order and structural correspondence between {src_lang} and {targ_lang} subtitles
2. Split the {targ_lang} subtitles according to the pre-processed {src_lang} split version
3. Never leave empty lines. If it's difficult to split based on meaning, you may appropriately rewrite the sentences that need to be aligned
4. Do not add comments or explanations in the translation, as the subtitles are for the audience to read

## INPUT
<subtitles>
{src_lang} Original: "{src_sub}"
{targ_lang} Original: "{tr_sub}"
Pre-processed {src_lang} Subtitles ([br] indicates split points): {src_part}
</subtitles>

## Output in only JSON format and no other text
```json
{{
    "analysis": "Brief analysis of word order, structure, and semantic correspondence between two subtitles",
    "align": [
        {align_parts_json}
    ]
}}
```

Note: Start you answer with ```json and end with ```, do not add any other text.
'''.strip()
    return align_prompt

## ================================================================
# @ step8_gen_audio_task.py @ step10_gen_audio.py
def get_subtitle_trim_prompt(text, duration):
 
    rule = '''Consider a. Reducing filler words without modifying meaningful content. b. Omitting unnecessary modifiers or pronouns, for example:
    - "Please explain your thought process" can be shortened to "Please explain thought process"
    - "We need to carefully analyze this complex problem" can be shortened to "We need to analyze this problem"
    - "Let's discuss the various different perspectives on this topic" can be shortened to "Let's discuss different perspectives on this topic"
    - "Can you describe in detail your experience from yesterday" can be shortened to "Can you describe yesterday's experience" '''

    trim_prompt = f'''
## Role
You are a professional subtitle editor, editing and optimizing lengthy subtitles that exceed voiceover time before handing them to voice actors. 
Your expertise lies in cleverly shortening subtitles slightly while ensuring the original meaning and structure remain unchanged.

## INPUT
<subtitles>
Subtitle: "{text}"
Duration: {duration} seconds
</subtitles>

## Processing Rules
{rule}

## Processing Steps
Please follow these steps and provide the results in the JSON output:
1. Analysis: Briefly analyze the subtitle's structure, key information, and filler words that can be omitted.
2. Trimming: Based on the rules and analysis, optimize the subtitle by making it more concise according to the processing rules.

## Output in only JSON format and no other text
```json
{{
    "analysis": "Brief analysis of the subtitle, including structure, key information, and potential processing locations",
    "result": "Optimized and shortened subtitle in the original subtitle language"
}}
```

Note: Start you answer with ```json and end with ```, do not add any other text.
'''.strip()
    return trim_prompt

## ================================================================
# @ tts_main
def get_correct_text_prompt(text):
    return f'''
## Role
You are a text cleaning expert for TTS (Text-to-Speech) systems.

## Task
Clean the given text by:
1. Keep only basic punctuation (.,?!)
2. Preserve the original meaning

## INPUT
{text}

## Output in only JSON format and no other text
```json
{{
    "text": "cleaned text here"
}}
```

Note: Start you answer with ```json and end with ```, do not add any other text.
'''.strip()

