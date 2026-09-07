from core.prompts import generate_shared_prompt, get_prompt_faithfulness, get_prompt_expressiveness
from rich.panel import Panel
from rich.console import Console
from rich.table import Table
from rich import box
from core.utils import *
console = Console()

def valid_translate_result(result: dict, required_keys: list, required_sub_keys: list):
    if not isinstance(result, dict):
        return {"status": "error", "message": "Translation result must be a JSON object"}

    missing = [key for key in required_keys if key not in result]
    unexpected = [key for key in result if key not in required_keys]
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"Missing required key(s): {', '.join(missing)}")
        if unexpected:
            details.append(f"Unexpected key(s): {', '.join(unexpected)}")
        return {"status": "error", "message": "; ".join(details)}
    
    # Check for required sub-keys in all items
    for key in required_keys:
        if not isinstance(result[key], dict):
            return {
                "status": "error",
                "message": f"Translation item {key} must be a JSON object",
            }
        if not all(sub_key in result[key] for sub_key in required_sub_keys):
            return {"status": "error", "message": f"Missing required sub-key(s) in item {key}: {', '.join(set(required_sub_keys) - set(result[key].keys()))}"}

    return {"status": "success", "message": "Translation completed"}

def translate_lines(
    lines,
    previous_content_prompt,
    after_cotent_prompt,
    things_to_note_prompt,
    summary_prompt,
    index=0,
    item_ids=None,
    video_style=None,
):
    check_cancel()
    source_lines = lines.split('\n')
    required_ids = (
        [str(i) for i in range(1, len(source_lines) + 1)]
        if item_ids is None
        else [str(item_id) for item_id in item_ids]
    )
    if len(required_ids) != len(source_lines):
        raise ValueError("item_ids must match the number of subtitle lines")
    if len(set(required_ids)) != len(required_ids):
        raise ValueError("item_ids must be unique")

    shared_prompt = generate_shared_prompt(
        previous_content_prompt,
        after_cotent_prompt,
        summary_prompt,
        things_to_note_prompt,
        video_style=video_style,
    )

    # Retry translation if the length of the original text and the translated text are not the same, or if the specified key is missing
    def retry_translation(prompt, step_name):
        def valid_faith(response_data):
            return valid_translate_result(response_data, required_ids, ['direct'])
        def valid_express(response_data):
            return valid_translate_result(response_data, required_ids, ['free'])
        for retry in range(3):
            if step_name == 'faithfulness':
                result = ask_gpt(prompt+retry* " ", resp_type='json', valid_def=valid_faith, log_title=f'translate_{step_name}')
                validation = valid_faith(result)
            elif step_name == 'expressiveness':
                result = ask_gpt(prompt+retry* " ", resp_type='json', valid_def=valid_express, log_title=f'translate_{step_name}')
                validation = valid_express(result)
            if validation["status"] == "success":
                return result
            if retry != 2:
                console.print(f'[yellow]⚠️ {step_name.capitalize()} translation of block {index} failed, Retry...[/yellow]')
        raise ValueError(f'[red]❌ {step_name.capitalize()} translation of block {index} failed after 3 retries. Please check `output/gpt_log/error.json` for more details.[/red]')

    ## Step 1: Faithful to the Original Text
    prompt1 = get_prompt_faithfulness(lines, shared_prompt, item_ids=item_ids)
    faith_result = retry_translation(prompt1, 'faithfulness')

    for item_id in required_ids:
        faith_result[item_id]["direct"] = faith_result[item_id]["direct"].replace('\n', ' ')

    # If reflect_translate is False or not set, use faithful translation directly
    reflect_translate = load_key('reflect_translate')
    if not reflect_translate:
        # If reflect_translate is False or not set, use faithful translation directly
        translate_result = "\n".join([faith_result[item_id]["direct"].strip() for item_id in required_ids])
        
        table = Table(title="Translation Results", show_header=False, box=box.ROUNDED)
        table.add_column("Translations", style="bold")
        for i, key in enumerate(required_ids):
            table.add_row(f"[cyan]Origin:  {faith_result[key]['origin']}[/cyan]")
            table.add_row(f"[magenta]Direct:  {faith_result[key]['direct']}[/magenta]")
            if i < len(required_ids) - 1:
                table.add_row("[yellow]" + "-" * 50 + "[/yellow]")
        
        console.print(table)
        return translate_result, lines

    ## Step 2: Express Smoothly  
    prompt2 = get_prompt_expressiveness(faith_result, lines, shared_prompt, item_ids=item_ids)
    express_result = retry_translation(prompt2, 'expressiveness')

    table = Table(title="Translation Results", show_header=False, box=box.ROUNDED)
    table.add_column("Translations", style="bold")
    for i, key in enumerate(required_ids):
        table.add_row(f"[cyan]Origin:  {faith_result[key]['origin']}[/cyan]")
        table.add_row(f"[magenta]Direct:  {faith_result[key]['direct']}[/magenta]")
        table.add_row(f"[green]Free:    {express_result[key]['free']}[/green]")
        if i < len(required_ids) - 1:
            table.add_row("[yellow]" + "-" * 50 + "[/yellow]")

    console.print(table)

    translate_result = "\n".join([express_result[item_id]["free"].replace('\n', ' ').strip() for item_id in required_ids])

    if len(lines.split('\n')) != len(translate_result.split('\n')):
        console.print(Panel(f'[red]❌ Translation of block {index} failed, Length Mismatch, Please check `output/gpt_log/translate_expressiveness.json`[/red]'))
        raise ValueError(f'Origin ···{lines}···,\nbut got ···{translate_result}···')

    return translate_result, lines


if __name__ == '__main__':
    # test e.g.
    lines = '''All of you know Andrew Ng as a famous computer science professor at Stanford.
He was really early on in the development of neural networks with GPUs.
Of course, a creator of Coursera and popular courses like deeplearning.ai.
Also the founder and creator and early lead of Google Brain.'''
    previous_content_prompt = None
    after_cotent_prompt = None
    things_to_note_prompt = None
    summary_prompt = None
    translate_lines(lines, previous_content_prompt, after_cotent_prompt, things_to_note_prompt, summary_prompt)
