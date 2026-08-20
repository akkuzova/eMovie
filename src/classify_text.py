"""
Quick manual test of the trained emotion classifier on arbitrary text.

Usage:
    python classify_text.py "This movie made me cry, in a good way."
"""
import sys

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_DIR = "models/emotion-classifier"

tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
model.eval()


def classify(text, top_k=5):
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.sigmoid(logits)[0]
    ranked = sorted(
        zip(model.config.id2label.values(), probs.tolist()), key=lambda x: -x[1]
    )
    return ranked[:top_k]


if __name__ == "__main__":
    text = " ".join(sys.argv[1:])
    if not text:
        print("Usage: python classify_text.py <text>")
        sys.exit(1)
    for label, score in classify(text):
        print(f"{label:15s} {score:.3f}")
