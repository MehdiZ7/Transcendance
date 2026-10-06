import type { Metadata } from "next";
import { LegalPage, type LegalSection } from "@/components/legal/LegalPage";

export const metadata: Metadata = {
  title: "Politique de confidentialité — LeBon42",
  description:
    "Comment LeBon42 collecte, utilise et protège vos données personnelles.",
};

const UPDATED_AT = "29 septembre 2026";

const sections: LegalSection[] = [
  {
    title: "Responsable du traitement",
    body: (
      <p>
        LeBon42 est une plateforme étudiante développée dans le cadre du projet
        ft_transcendence de l’école 42. Le responsable du traitement des données
        est l’équipe LeBon42. Pour toute question relative à vos données, vous
        pouvez nous contacter via l’espace Messages de l’application ou le dépôt
        du projet.
      </p>
    ),
  },
  {
    title: "Données que nous collectons",
    body: (
      <ul className="list-disc pl-5 space-y-1">
        <li>
          <span className="font-medium text-slate-700">Compte :</span> lors de
          votre connexion via l’API 42 (OAuth), nous récupérons votre identifiant
          intra, votre adresse e-mail, votre nom d’affichage et votre photo de
          profil. Si vous créez un compte avec une adresse e-mail et un mot de
          passe, nous conservons votre adresse, votre nom d’affichage et une
          empreinte (hachage) de votre mot de passe, jamais le mot de passe
          lui-même.
        </li>
        <li>
          <span className="font-medium text-slate-700">Profil :</span> biographie
          et avatar, que vous pouvez modifier à tout moment.
        </li>
        <li>
          <span className="font-medium text-slate-700">Contenus publiés :</span>{" "}
          annonces, messages, avis et notes, favoris et signalements.
        </li>
        <li>
          <span className="font-medium text-slate-700">Données techniques :</span>{" "}
          cookie de session, adresse IP dans les journaux du serveur et métriques
          d’usage agrégées.
        </li>
      </ul>
    ),
  },
  {
    title: "Pourquoi nous les utilisons",
    body: (
      <ul className="list-disc pl-5 space-y-1">
        <li>Vous authentifier et sécuriser l’accès à votre compte.</li>
        <li>
          Faire fonctionner la marketplace : annonces, recherche, favoris et
          messagerie.
        </li>
        <li>Assurer la modération, notamment le traitement des signalements.</li>
        <li>
          Produire des statistiques internes (nombre d’annonces, taux de vente),
          sous forme agrégée.
        </li>
      </ul>
    ),
  },
  {
    title: "Base légale",
    body: (
      <p>
        Le traitement repose sur l’exécution du service que vous demandez (vous
        connecter, publier une annonce), sur votre consentement (par exemple pour
        votre photo de profil) et sur l’intérêt légitime de l’équipe à sécuriser
        et à modérer la plateforme.
      </p>
    ),
  },
  {
    title: "Cookies et session",
    body: (
      <p>
        LeBon42 n’utilise que des cookies strictement nécessaires : un cookie de
        session (jeton signé) qui vous maintient connecté, et, uniquement pendant
        une connexion via 42, deux cookies temporaires (état et destination)
        supprimés dès la connexion terminée. Le cookie de session est HttpOnly,
        SameSite=Lax et Secure. Nous n’utilisons aucun cookie publicitaire ni
        traceur tiers.
      </p>
    ),
  },
  {
    title: "Destinataires et services tiers",
    body: (
      <ul className="list-disc pl-5 space-y-1">
        <li>
          L’API 42 est utilisée uniquement pour l’authentification (OAuth). Le
          jeton d’accès 42 n’est jamais conservé.
        </li>
        <li>
          La plateforme est hébergée sur l’infrastructure du projet, sous forme de
          conteneurs.
        </li>
        <li>
          Prometheus et Grafana collectent des métriques techniques agrégées, sans
          données personnelles.
        </li>
        <li>
          Vos données ne sont ni revendues ni transmises à des fins commerciales.
        </li>
      </ul>
    ),
  },
  {
    title: "Durée de conservation",
    body: (
      <p>
        La session expire après 7 jours. Les données de compte et les contenus
        publiés sont conservés tant que votre compte existe. En cas de
        suppression, les données sont effacées ou anonymisées.
      </p>
    ),
  },
  {
    title: "Vos droits",
    body: (
      <p>
        Conformément au RGPD, vous disposez d’un droit d’accès, de rectification,
        d’effacement, de limitation, d’opposition et de portabilité. La plupart
        de vos informations sont modifiables depuis votre profil. Pour exercer vos
        droits, contactez un admin de l’équipe LeBon42.
      </p>
    ),
  },
  {
    title: "Sécurité",
    body: (
      <p>
        Les échanges sont chiffrés (HTTPS/TLS). L’authentification repose sur 42
        OAuth ou sur un couple e-mail / mot de passe : dans ce second cas, le mot
        de passe est haché (Argon2) et n’est jamais stocké en clair. Les secrets
        (clés et identifiants de base de données) sont gérés séparément et ne
        sont jamais exposés.
      </p>
    ),
  },
  {
    title: "Modifications",
    body: (
      <p>
        Cette politique peut être mise à jour. La date de dernière mise à jour
        figure en haut de cette page.
      </p>
    ),
  },
  {
    title: "Contact",
    body: (
      <p>
        Pour toute question relative à vos données personnelles, contactez un admin
        de l’équipe LeBon42 via l’espace Messages de l’application ou le dépôt du
        projet.
      </p>
    ),
  },
];

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Politique de confidentialité"
      updatedAt={UPDATED_AT}
      sections={sections}
    />
  );
}
