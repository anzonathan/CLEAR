#!/usr/bin/env python3
"""Train / fine-tune CLEAR YOLO detector (two-phase freeze/unfreeze transfer learning per README Section 7)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="CLEAR: Two-phase YOLO transfer learning trainer.")
    parser.add_argument("--config", type=str, default="configs/detector.yaml", help="Detector config YAML")
    parser.add_argument("--data", type=str, default="data/ucu_clay.yaml", help="YOLO dataset YAML")
    parser.add_argument("--epochs-stage1", type=int, default=15, help="Stage 1 epochs (frozen backbone)")
    parser.add_argument("--epochs-stage2", type=int, default=35, help="Stage 2 epochs (unfrozen full fine-tune)")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and print training plan without GPU run")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}

    plan = {
        "project": cfg.get("project", "CLEAR"),
        "base_weights": cfg.get("detector", {}).get("yolo_weights", "yolov8n.pt"),
        "imgsz": cfg.get("detector", {}).get("imgsz", 640),
        "stage1_frozen_backbone": {"epochs": args.epochs_stage1, "freeze": 10, "lr0": 1e-3},
        "stage2_full_finetune": {"epochs": args.epochs_stage2, "freeze": 0, "lr0": 2e-4},
        "dataset_yaml": args.data,
    }

    if args.dry_run or not Path(args.data).exists():
        print(
            json.dumps(
                {
                    "status": "ready_for_ucu_dataset",
                    "note": "Dataset YAML not yet populated or --dry-run passed. Use zero-shot hybrid pipeline or supply CVAT YOLO export at data/ucu_clay.yaml.",
                    "training_plan": plan,
                },
                indent=2,
            )
        )
        return

    from ultralytics import YOLO  # type: ignore

    model = YOLO(plan["base_weights"])
    # Stage 1: Freeze first 10 backbone layers
    model.train(
        data=args.data,
        epochs=args.epochs_stage1,
        imgsz=plan["imgsz"],
        freeze=10,
        lr0=1e-3,
        project="models",
        name="clear_stage1",
    )
    # Stage 2: Unfreeze all layers at lower learning rate
    model.train(
        data=args.data,
        epochs=args.epochs_stage2,
        imgsz=plan["imgsz"],
        freeze=0,
        lr0=2e-4,
        project="models",
        name="clear_stage2_final",
    )


if __name__ == "__main__":
    main()
