#!/usr/bin/env python
"""Thin CLI wrapper so training can be run as ``python scripts/train_valuation_model.py`` from
the ``backend/`` directory, matching the "bootstrap script" deployment requirement in PRD
section 9. Delegates entirely to ``app.ml.train`` (SRP — this file has no logic of its own).
"""

from app.ml.train import main

if __name__ == "__main__":
    main()
