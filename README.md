# Control Plane IAM

Service d'autorisation centralisé : « l'utilisateur X a-t-il le droit de faire l'action Y sur le projet Z ? »

Chaque décision est expliquée par la règle qui a tranché : Global Owner, puis override DENY, puis override ALLOW, puis droit de groupe, sinon refus par défaut.

## Statut

🚧 En cours de développement (v1), pas encore utilisable.

## Prérequis

- Python 3.14
- [uv](https://docs.astral.sh/uv/)
- Docker (PostgreSQL 16)

## Installation

```bash
uv sync
cp .env.example .env   # puis remplacer les valeurs factices
```

## Licence

MIT, voir [LICENSE](LICENSE).
