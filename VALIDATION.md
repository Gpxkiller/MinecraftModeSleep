# Validation 0.1.0

Préversion expérimentale. Aucun VPS ni serveur réel de l'auteur n'est modifié pour cette publication.

## Portable

- Python : décisions d'inactivité, compteur récent/absent/périmé/invalide, joueurs présents et connexions physiques invisibles, arrivée concurrente, garde d'admission et libération après exception, fermeture/ouverture explicite, demandes persistantes, réveil unique, disponibilité, échec/timeout et reprise après redémarrage.
- Parseur TCP : IPv4 loopback, connexions établies/en cours, autres ports, TIME_WAIT, listener public/IPv6 et état inconnu.
- Protocole : véritables sockets loopback de laboratoire pour réponses de statut Minecraft fictives, JSON invalide et comptes négatifs refusés.
- Java : sessions indépendantes, reconnexion au même UUID, changement de destination, timeout monotone, file bornée, transfert unique et callback d'une ancienne demande ne supprimant pas la nouvelle.

Les données des fixtures sont inventées. Les appels systemd dans les tests de politique sont simulés, pas présentés comme des arrêts réels de Paper.

## Linux privilégié

`tests/test_kernel.py` ne s'active qu'avec `MODESLEEP_NETNS_TEST=1`, root et un namespace réseau différent de PID1. La CI lance le test dans `unshare --net` et non sur le pare-feu de l'hôte.

Scénarios : une connexion cible existante reste utilisable ; de nouvelles connexions cibles sont refusées ; un autre serveur reste joignable ; retrait exact de la garde après exception ; récupération d'un bail interrompu ; comparaison du pare-feu avant/après.

Ne pas annoncer ces tests réussis avant une CI verte. Sous Windows, les trois tests noyau et le test de lien symbolique sont ignorés volontairement.

## Limites de preuve

Contrôle Windows : 60 tests Python exécutés, quatre ignorés (netfilter/symlink) et dix tests Java réussis, dont le débordement signé de l'horloge monotone. Un vrai Velocity 4.2.1 de laboratoire charge le plugin activé, écoute seulement sur loopback, publie le heartbeat et refuse de supposer le worker prêt lorsque son état est périmé ; arrêt console officiel réussi. Ce contrôle n'est pas un transfert humain ni un test systemd Linux.

Les tests de files de joueurs ne sont pas des parties humaines. Le code ne modifie ni droits Minecraft, ni inventaires, ni mondes. Geyser/Bedrock utilise le même événement Velocity mais une compatibilité humaine universelle n'est pas revendiquée. Un démarrage réel du plugin et une CI Linux verte doivent être vérifiés avant la publication de l'archive.
