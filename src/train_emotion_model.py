"""
Fine-tune a small transformer on GoEmotions for multi-label emotion classification.

Runs fully locally (Apple Silicon GPU via MPS if available) — no API costs,
so it scales to however many scraped reviews you throw at it at inference time.

Usage:
    conda activate emovie-train
    python train_emotion_model.py
"""
import numpy as np
import torch
from datasets import load_dataset
from sklearn.metrics import f1_score
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)

MODEL_NAME = "distilbert-base-uncased"
OUTPUT_DIR = "../models/emotion-classifier"
MAX_LENGTH = 128

device = "mps" if torch.backends.mps.is_available() else "cpu"
print(f"Using device: {device}")

dataset = load_dataset("google-research-datasets/go_emotions", "simplified")
label_names = dataset["train"].features["labels"].feature.names
num_labels = len(label_names)
print(f"{num_labels} labels: {label_names}")

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)


def preprocess(batch):
    encoded = tokenizer(batch["text"], truncation=True, max_length=MAX_LENGTH)
    # multi-hot encode the label list into a fixed-width float vector
    multi_hot = np.zeros((len(batch["labels"]), num_labels), dtype=np.float32)
    for i, labels in enumerate(batch["labels"]):
        multi_hot[i, labels] = 1.0
    encoded["labels"] = multi_hot.tolist()
    return encoded


dataset = dataset.map(preprocess, batched=True, remove_columns=["text", "id"])
dataset.set_format("torch")

model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME,
    num_labels=num_labels,
    problem_type="multi_label_classification",
    id2label={i: name for i, name in enumerate(label_names)},
    label2id={name: i for i, name in enumerate(label_names)},
).to(device)


base_collator = DataCollatorWithPadding(tokenizer)


def data_collator(features):
    # DataCollatorWithPadding forces "labels" to long dtype, which breaks
    # BCEWithLogitsLoss for multi-label classification — cast back to float.
    batch = base_collator(features)
    batch["labels"] = batch["labels"].float()
    return batch


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    probs = 1 / (1 + np.exp(-logits))  # sigmoid
    preds = (probs > 0.5).astype(int)
    return {
        "f1_micro": f1_score(labels, preds, average="micro", zero_division=0),
        "f1_macro": f1_score(labels, preds, average="macro", zero_division=0),
    }


training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    eval_strategy="epoch",
    save_strategy="epoch",
    learning_rate=2e-5,
    per_device_train_batch_size=32,
    per_device_eval_batch_size=64,
    num_train_epochs=3,
    weight_decay=0.01,
    load_best_model_at_end=True,
    metric_for_best_model="f1_micro",
    report_to="none",
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset["train"],
    eval_dataset=dataset["validation"],
    processing_class=tokenizer,
    data_collator=data_collator,
    compute_metrics=compute_metrics,
)

trainer.train()
print(trainer.evaluate(dataset["test"]))

trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"Saved model to {OUTPUT_DIR}")
