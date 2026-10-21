# MinecraftModeSleep

**Mise en veille et réveil automatique de serveurs Minecraft derrière Velocity.**

Projet autonome de Gpxkiller, licence MIT. Préversion expérimentale **0.1.0**.
Les exemples ne contiennent aucune configuration ni donnée d'un serveur réel.

## Ce que fait le projet

- Après 24 heures sans joueur (durée configurable par mode), arrêt du backend vide pour libérer ses ressources.
- Une tentative de connexion réveille un mode en veille. Le joueur attend sur son serveur actuel ou au lobby, puis est transféré après confirmation du démarrage.
- Plusieurs joueurs demandant le même mode partagent une seule demande de réveil.
- Un changement de destination, une déconnexion ou une nouvelle session invalide l'ancien transfert.
- **Fermer volontairement n'est pas mettre en veille** : une connexion ne rouvre jamais un mode fermé volontairement.
- Le lobby et le proxy ne doivent jamais figurer parmi les modes gérés ; les ports et unités protégés sont refusés.
- Les commandes de maintenance restent des commandes locales d'opérateur Linux, pas des droits donnés aux joueurs.

Pas de site hébergé, pas de compte cloud, pas de token, pas de console distante.
Pas de dépendance aux plugins GPX, à un panel web ou à un nom de domaine.

## Architecture et compatibilité

1. Un plugin **Velocity 4.2.1-SNAPSHOT / Java 25+** observe les joueurs (staff invisible compris), les intentions de transfert et les sessions.
2. Un petit service **Linux + systemd + iptables + Python 3.10+** contrôle uniquement les unités configurées.
3. Échange de fichiers atomiques sur le même hôte ; aucune API réseau d'administration.

Le choix de l'API suit la [documentation officielle Velocity](https://docs.papermc.io/velocity/dev/creating-your-first-plugin/). Aucun support revendiqué pour BungeeCord, Windows comme hôte du worker, les hébergements sans contrôle système, Docker/Pterodactyl ou plusieurs machines. Java et Bedrock derrière un même Velocity utilisent le même chemin de transfert ; cette préversion n'a pas de preuve de partie humaine Bedrock.

**Restriction importante : backends accessibles uniquement en IPv4 sur `127.0.0.1`.** Un listener public, IPv6 ou inconnu empêche l'arrêt. Ne pas exposer ces ports directement aux joueurs. Les unités systemd doivent avoir un arrêt propre, suffisamment long pour sauvegarder le monde et sans terminaison forcée. Le projet n'écrit jamais dans les mondes et n'en crée pas de sauvegarde à votre place.

## Protections

Avant un arrêt, il faut un relevé Velocity récent et exactement zéro joueur. Le worker pose ensuite une garde temporaire qui refuse seulement les **nouvelles** connexions TCP du backend choisi, relit toutes ses connexions physiques (y compris les connexions en cours), puis demande son arrêt propre. Une session existante ou un état douteux annule l'opération. Aucun `/reload`, `/kick` ou arrêt de proxy n'est exécuté.

La garde est retirée après l'opération. Son bail est persistant : le passage suivant récupère seulement les règles portant son identifiant exact après un crash. Le pare-feu n'est jamais vidé. Un arrêt interrompu est réconcilié avec l'état systemd ; un échec de démarrage ne devient pas une fausse confirmation de disponibilité.

L'attente d'un joueur est bornée à trois minutes. Un réveil non confirmé est signalé comme indisponible : aucune boucle de redémarrage illimitée. Les opérations inconnues ne démarrent pas un service arrêté arbitrairement. Les whitelists, permissions et contrôles de connexion des autres plugins/backends restent applicables.

## Construire et tester

```sh
mvn -B package
python3 -m unittest discover -s tests -p 'test_*.py'
```

Le plugin est `target/minecraft-mode-sleep-0.1.0.jar`. Python n'a aucune dépendance externe.
Les tests privilégiés sont désactivés par défaut et ne doivent être lancés que dans un **namespace réseau jetable**, jamais sur le pare-feu d'un serveur en service. Voir `VALIDATION.md`.

## Installer sur son propre hôte (manuel)

Lire d'abord `SECURITY.md`. Ne pas appliquer ces étapes à un serveur occupé : préparer puis redémarrer officiellement le proxy lorsque le réseau est vide. Cette publication n'installe rien automatiquement.

1. Préparer un groupe système dédié, par exemple `modesleep`. Ajouter **seulement le compte système du proxy** à ce groupe. Le proxy ne doit pas tourner comme root. Le worker tourne séparément comme root pour systemd et netfilter.
2. Créer `/var/lib/minecraft-mode-sleep` (root, `0755`), ses sous-dossiers `private` (root, `0700`), `public` (root, `0755`) et `inbox` (root:groupe-dédié, `0770`). Aucun de ces chemins ne doit être un lien symbolique. Le proxy peut lire `public` et écrire seulement `inbox`, jamais `private`.
3. Copier `daemon/modesleep.py` dans `/usr/local/lib/minecraft-mode-sleep/` et l'exemple `daemon/config.example.json` dans `/etc/minecraft-mode-sleep/config.json`. Le code et le fichier de configuration doivent appartenir à root et être non modifiables par le proxy. Adapter les modes, unités et ports, sans ajouter le lobby ni le proxy. Ajouter leurs vrais ports/unités à `protectedPorts` et `protectedUnits` si les noms par défaut ne correspondent pas.
4. Vérifier la configuration :

   ```sh
   python3 /usr/local/lib/minecraft-mode-sleep/modesleep.py --config /etc/minecraft-mode-sleep/config.json check
   ```

5. Copier le JAR dans `plugins/` du proxy. Son premier démarrage génère une configuration **désactivée** dans `plugins/minecraftmodesleep/config.json`. Adapter `ipcRoot`, `lobby` et la correspondance des identifiants de modes avec les noms enregistrés dans `velocity.toml`. Les identifiants doivent être les mêmes des deux côtés. Ne pas gérer un backend qui partage le port du lobby.
6. Mettre `enabled: true` dans les deux configurations. Copier les exemples systemd de `deploy/`, puis les charger et activer le timer avec les outils habituels de votre distribution. Les unités des backends doivent déjà exister et accepter un arrêt propre. Installer iptables s'il n'est pas présent ; aucun changement de politique globale de pare-feu n'est requis par le projet.
7. Redémarrer officiellement le proxy à vide pour charger sa configuration. Tester un mode **de laboratoire** avec `sleep`, puis le rejoindre via votre sélecteur habituel. Le plugin n'ajoute pas de menu ; un sélecteur qui masque les serveurs éteints doit être configuré pour conserver ceux en veille.

La période d'inactivité commence à l'activation, sans inventer un historique de 24 heures. Un relevé périmé, manquant ou invalide remet le compteur d'inactivité à zéro.

## Commandes locales de l'opérateur

Toutes les mutations exigent root et `--apply` explicite. Exemple de préfixe :

```sh
sudo python3 /usr/local/lib/minecraft-mode-sleep/modesleep.py --config /etc/minecraft-mode-sleep/config.json --apply sleep arena
sudo python3 /usr/local/lib/minecraft-mode-sleep/modesleep.py --config /etc/minecraft-mode-sleep/config.json --apply close arena
sudo python3 /usr/local/lib/minecraft-mode-sleep/modesleep.py --config /etc/minecraft-mode-sleep/config.json --apply open arena
```

- `sleep` : demande persistante de veille, exécutée uniquement lorsqu'il est vide et vérifié.
- `close` : ferme l'accès ; les joueurs présents ne sont pas expulsés. Arrêt seulement après confirmation de vacuité. Aucune connexion ne le réouvre.
- `open` : autorise de nouveau les connexions. Un mode arrêté volontairement peut alors être réveillé à sa prochaine tentative d'entrée. Cette action explicite d'opérateur est distincte d'un réveil automatique.
- `tick` : passage unique du worker (normalement appelé par le timer).
- `check` : validation seule, sans `--apply` et sans contrôle de service.

Journaux : journal systemd, seulement identifiants des modes et résultats, sans pseudos/IP joueurs. Les exemples n'incluent aucun administrateur préconfiguré.

## Limites

Préversion, pas une garantie de zéro bug ni de compatibilité universelle. Les tests simulés de sessions ne remplacent pas des essais humains Java/Bedrock. Arrêter un backend invalide ses sessions locales ; aucune opération ne doit contourner la garde de vacuité. Les autres outils de déploiement/maintenance doivent se coordonner avec l'opérateur : ce service n'a pas autorité sur leurs verrous ni sur les actions root extérieures. Voir `VALIDATION.md` pour les preuves effectivement obtenues.

## English

MIT-licensed single-host backend sleep/wake for Velocity. Separate root Linux worker, unprivileged proxy, explicit systemd unit/port allowlist, temporary exact-token IPv4 loopback SYN gate, fresh player heartbeat, physical connection recheck, persistent manual closure and session-aware pending joins. Disabled by default. Experimental; no production configuration or player data included.
