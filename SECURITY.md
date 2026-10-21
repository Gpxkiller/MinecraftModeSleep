# Sécurité

- Ne jamais exécuter le proxy comme root. Le groupe dédié ne doit accéder qu'à l'inbox, pas au code/config/état privé du worker.
- Le worker est privilégié : sa configuration décide des unités qu'il peut démarrer/arrêter. Vérifier les correspondances, ports et unités protégés. Un administrateur root malveillant ou une configuration erronée ne peut pas être neutralisé par ce plugin.
- Backends sur le même hôte, liés exclusivement à `127.0.0.1` IPv4. Aucun support des arrivées directes depuis Internet, d'IPv6 backend ou de plusieurs hôtes.
- Ne pas exposer le dossier IPC par HTTP. Ne jamais publier des configurations réelles, mondes, comptes, journaux ou données de joueurs.
- Le compteur Velocity ne suffit pas : le garde SYN et `/proc/net/tcp*` sont obligatoires. Ne pas remplacer les erreurs par zéro.
- Les règles de pare-feu sont temporaires et identifiées par bail exact. Une récupération doit conserver toutes les autres règles. Ne pas vider une chaîne de pare-feu pour débloquer le service.
- Une unité backend doit sauvegarder et s'arrêter proprement, sans `kill -9` ni terminaison forcée après délai. Le worker ne peut pas rendre sûre une unité systemd mal configurée.
- Une fermeture manuelle reste prioritaire. Aucun réveil d'un service arbitrairement arrêté sans marqueur de veille ou action explicite `open`.
- Désactiver le timer avant une maintenance manuelle concurrente, puis le réactiver après vérification. Aucun arrêt automatique du lobby/proxy ne fait partie des fonctionnalités.

Pour signaler un problème : fournir un scénario minimal avec configuration **fictive**, jamais des identifiants ou données privées. Les problèmes de permissions, de ciblage de service ou de garde d'admission doivent être traités avant toute installation réelle.
