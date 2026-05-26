"""
Parse AI Hub 필수의료 의학지식 데이터 into LLM training format.
Extracts QA pairs from labeled data (라벨링데이터) for SFT fine-tuning.

Usage: python -m scripts.parse_aihub_qa
"""

import json
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = Path(__file__).parent.parent / "data" / "aihub"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "training"


def extract_and_parse_zip(zip_path: Path) -> list[dict]:
    """Extract a zip file and parse all JSON files inside."""
    records = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name.endswith('.json'):
                    with zf.open(name) as f:
                        try:
                            raw = f.read()
                            text = raw.decode('utf-8-sig')  # Handle BOM
                            data = json.loads(text)
                            parsed = parse_json_record(data, zip_path.stem)
                            if parsed:
                                records.extend(parsed)
                        except (json.JSONDecodeError, UnicodeDecodeError) as e:
                            print(f"    Warning: Could not parse {name}: {e}")
    except zipfile.BadZipFile:
        print(f"    Warning: Bad zip file: {zip_path.name}")
    return records


def parse_json_record(data: dict, source_name: str) -> list[dict]:
    """Parse a single JSON record into QA training format.
    AI Hub medical QA data can have various structures."""
    records = []

    # Try different possible structures
    if isinstance(data, list):
        for item in data:
            parsed = extract_qa_from_item(item, source_name)
            if parsed:
                records.extend(parsed)
    elif isinstance(data, dict):
        # Check for common AI Hub structures
        if 'data' in data:
            items = data['data'] if isinstance(data['data'], list) else [data['data']]
            for item in items:
                parsed = extract_qa_from_item(item, source_name)
                if parsed:
                    records.extend(parsed)
        elif 'question' in data or 'Q' in data or 'input' in data:
            parsed = extract_qa_from_item(data, source_name)
            if parsed:
                records.extend(parsed)
        elif 'paragraphs' in data:
            for para in data['paragraphs']:
                parsed = extract_qa_from_item(para, source_name)
                if parsed:
                    records.extend(parsed)
        else:
            # Try to extract from any nested structure
            parsed = extract_qa_from_item(data, source_name)
            if parsed:
                records.extend(parsed)

    return records


def extract_qa_from_item(item: dict, source_name: str) -> list[dict]:
    """Extract question-answer pair from a single item."""
    if not isinstance(item, dict):
        return []

    records = []

    # Try various key patterns used in AI Hub datasets
    q_keys = ['question', 'Q', 'input', 'query', '질문', 'user_query', 'instruction']
    a_keys = ['answer', 'A', 'output', 'response', '답변', 'assistant_response', 'completion']
    ctx_keys = ['context', 'passage', 'reference', '참고문헌', 'source_text', 'paragraph']

    question = None
    answer = None
    context = None

    for k in q_keys:
        if k in item and item[k]:
            question = str(item[k]).strip()
            break

    for k in a_keys:
        if k in item and item[k]:
            answer = str(item[k]).strip()
            break

    for k in ctx_keys:
        if k in item and item[k]:
            context = str(item[k]).strip()
            break

    if question and answer:
        record = {
            "instruction": question,
            "output": answer,
            "source": source_name,
        }
        if context:
            record["input"] = context
        records.append(record)

    # Check for nested QA pairs (some datasets have 'qas' array)
    if 'qas' in item:
        for qa in item['qas']:
            sub = extract_qa_from_item(qa, source_name)
            records.extend(sub)

    return records


def parse_source_text(zip_path: Path) -> list[dict]:
    """Parse source/reference text files for continued pre-training corpus."""
    texts = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name.endswith('.json'):
                    with zf.open(name) as f:
                        try:
                            raw = f.read()
                            text = raw.decode('utf-8-sig')
                            data = json.loads(text)
                            extracted = extract_text_content(data, zip_path.stem)
                            texts.extend(extracted)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass
                elif name.endswith('.txt'):
                    with zf.open(name) as f:
                        try:
                            content = f.read().decode('utf-8-sig').strip()
                            if len(content) > 50:
                                texts.append({
                                    "text": content,
                                    "source": zip_path.stem,
                                })
                        except UnicodeDecodeError:
                            pass
    except zipfile.BadZipFile:
        pass
    return texts


def extract_text_content(data, source_name: str) -> list[dict]:
    """Extract text content from various JSON structures."""
    texts = []

    if isinstance(data, str) and len(data) > 50:
        texts.append({"text": data, "source": source_name})
    elif isinstance(data, list):
        for item in data:
            texts.extend(extract_text_content(item, source_name))
    elif isinstance(data, dict):
        text_keys = ['text', 'content', 'passage', 'paragraph', 'body', 'abstract',
                     '본문', '내용', 'document', 'article']
        for k in text_keys:
            if k in data and isinstance(data[k], str) and len(data[k]) > 50:
                texts.append({"text": data[k], "source": source_name})

        # Recurse into nested structures
        for k, v in data.items():
            if isinstance(v, (list, dict)):
                texts.extend(extract_text_content(v, source_name))

    return texts


def main():
    print("=" * 60)
    print("AI Hub Medical QA Data Parser")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Find all zip files
    zip_files = list(DATA_DIR.rglob("*.zip"))
    if not zip_files:
        print(f"\nNo zip files found in {DATA_DIR}")
        return

    print(f"\nFound {len(zip_files)} zip files")

    # Separate labeled data (QA pairs) from source data (corpus)
    label_zips = [z for z in zip_files if '라벨링' in str(z) or 'TL_' in z.name or 'VL_' in z.name]
    source_zips = [z for z in zip_files if '원천' in str(z) or 'TS_' in z.name]

    # ── Parse QA pairs (labeled data) ──
    print(f"\n{'─' * 50}")
    print(f"Parsing QA pairs from {len(label_zips)} labeled data files...")
    all_qa = []
    for zip_path in sorted(label_zips):
        print(f"  {zip_path.name}...", end=" ")
        qa_records = extract_and_parse_zip(zip_path)
        all_qa.extend(qa_records)
        print(f"{len(qa_records)} QA pairs")

    # ── Parse source texts (corpus for pre-training) ──
    print(f"\n{'─' * 50}")
    print(f"Parsing source texts from {len(source_zips)} source data files...")
    all_texts = []
    for zip_path in sorted(source_zips):
        print(f"  {zip_path.name}...", end=" ")
        texts = parse_source_text(zip_path)
        all_texts.extend(texts)
        print(f"{len(texts)} text segments")

    # ── Save QA pairs ──
    if all_qa:
        # Save as JSONL (standard LLM training format)
        qa_path = OUTPUT_DIR / "aihub_medical_qa.jsonl"
        with open(qa_path, 'w', encoding='utf-8') as f:
            for record in all_qa:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        print(f"\n  QA pairs saved: {len(all_qa)} → {qa_path.name}")

        # Show samples
        print(f"\n  Sample QA pairs:")
        for i, qa in enumerate(all_qa[:3]):
            q = qa['instruction'][:80] + "..." if len(qa['instruction']) > 80 else qa['instruction']
            a = qa['output'][:80] + "..." if len(qa['output']) > 80 else qa['output']
            print(f"    [{i+1}] Q: {q}")
            print(f"        A: {a}")
            print()
    else:
        print("\n  WARNING: No QA pairs extracted. Checking raw JSON structure...")
        # Debug: show first JSON structure
        for zip_path in label_zips[:1]:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for name in zf.namelist()[:1]:
                    if name.endswith('.json'):
                        with zf.open(name) as f:
                            data = json.loads(f.read().decode('utf-8'))
                            if isinstance(data, dict):
                                print(f"    JSON keys: {list(data.keys())[:20]}")
                                for k, v in list(data.items())[:5]:
                                    v_str = str(v)[:200]
                                    print(f"    {k}: {v_str}")
                            elif isinstance(data, list):
                                print(f"    JSON is list with {len(data)} items")
                                if data:
                                    first = data[0]
                                    if isinstance(first, dict):
                                        print(f"    First item keys: {list(first.keys())[:20]}")

    # ── Save source texts ──
    if all_texts:
        corpus_path = OUTPUT_DIR / "aihub_medical_corpus.jsonl"
        with open(corpus_path, 'w', encoding='utf-8') as f:
            for text in all_texts:
                f.write(json.dumps(text, ensure_ascii=False) + '\n')
        print(f"  Medical corpus saved: {len(all_texts)} segments → {corpus_path.name}")

    # ── Summary ──
    print(f"\n{'=' * 60}")
    print("AI HUB PARSING COMPLETE")
    print(f"{'=' * 60}")
    print(f"  QA pairs (for SFT):     {len(all_qa)}")
    print(f"  Text segments (corpus):  {len(all_texts)}")
    by_source = {}
    for qa in all_qa:
        s = qa.get('source', 'unknown')
        by_source[s] = by_source.get(s, 0) + 1
    if by_source:
        print(f"\n  QA pairs by department:")
        for source, count in sorted(by_source.items()):
            print(f"    {source}: {count}")


if __name__ == "__main__":
    main()
