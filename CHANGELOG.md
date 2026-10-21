# Changements

## 0.1.1

- Le relevé public reste lisible par le proxy non privilégié malgré l'umask restrictif de systemd ; le journal privé reste en 0600.

- Une déconnexion ou un événement tardif de l'ancienne session ne supprime plus l'attente de la nouvelle connexion du même joueur.
- Les nouvelles arrivées renouvellent atomiquement l'unique demande de réveil, même si le fichier précédent est périmé.
- Fermer un mode invalide ses anciennes demandes ; rouvrir annule une demande de veille encore en attente et réinitialise l'inactivité.
- Un mode fermé redémarré extérieurement est de nouveau arrêté uniquement une fois vide, sous la garde habituelle.
- Régressions : 200 sessions concurrentes avec reconnexions, 100 passages de worker, fermeture pendant démarrage et renouvellement des demandes. Préversion, aucun essai humain ni serveur de production revendiqué.

## 0.1.0

- Extraction autonome du principe de veille/réveil : aucune dépendance GPX ni configuration de production.
- Plugin Velocity : attente sur place/lobby, file bornée, requête unique par mode et protection des nouvelles sessions/choix de destination.
- Worker Linux : inactivité configurable, unités/ports autorisés, fermeture manuelle persistante, garde SYN temporaire et vérification des connexions physiques.
- Configurations désactivées par défaut, licence MIT, documentation et tests isolés.
- Préversion expérimentale, installation manuelle uniquement.
