"""Adapter layer that turns the agent pipeline into the shapes the Homerun UI renders.

The agents/services under ``app.agents`` / ``app.services`` stay UI-agnostic; this package owns
the translation (listing view models, the UI's four preference sliders, short exclusion reasons,
viewing/hub persistence) so the frontend design never dictates changes to the domain layer.
"""
