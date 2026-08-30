"""Durable memory for the agents that claim to remember.

Today: Date Studio preferences, plan snapshots and feedback, in SQLite.

The interface is deliberately narrow because AgentCore Memory is the intended
replacement. It is a TARGET, not a completed integration — nothing here talks to
it, and no documentation may say otherwise.
"""
