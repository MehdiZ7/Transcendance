import type { Metadata } from "next";
import { LegalPage, type LegalSection } from "@/components/legal/LegalPage";

export const metadata: Metadata = {
  title: "Conditions d’utilisation — LeBon42",
  description:
    "Les règles d’utilisation de LeBon42, la marketplace étudiante de l’école 42.",
};

const UPDATED_AT = "29 septembre 2026";

const sections: LegalSection[] = [
  {
    title: "Objet et acceptation",
    body: (
      <p>
        En accédant à LeBon42 et en vous connectant, vous acceptez les présentes
        conditions d’utilisation. Si vous ne les acceptez pas, vous ne devez pas
        utiliser le service.
      </p>
    ),
  },
  {
    title: "Le service",
    body: (
      <p>
        LeBon42 est une plateforme de petites annonces et d’entraide réservée aux
        étudiants de l’école 42 : vente d’objets, tutorat et cours, covoiturage et
        services. Le service est fourni à titre gratuit et non commercial.
      </p>
    ),
  },
  {
    title: "Votre compte",
    body: (
      <p>
        L’accès se fait soit via votre compte 42 (OAuth), soit via un compte créé
        avec une adresse e-mail et un mot de passe. Dans ce second cas, le mot de
        passe est conservé sous forme hachée (Argon2), jamais en clair. Vous êtes
        responsable de la confidentialité de votre mot de passe, de l’exactitude
        des informations de votre profil et de l’usage de votre compte. Un compte
        par personne.
      </p>
    ),
  },
  {
    title: "Règles de publication",
    body: (
      <>
        <p>
          Vous ne publiez que des contenus licites, exacts et dont vous avez le
          droit de disposer. Chaque annonce doit indiquer un prix clair et un
          campus correct.
        </p>
        <p>Sont notamment interdits :</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>les biens illégaux, dangereux ou réglementés (armes, drogues…) ;</li>
          <li>les contrefaçons et les produits volés ;</li>
          <li>
            les contenus haineux, harcelants, violents, pornographiques ou
            diffamatoires ;
          </li>
          <li>le spam et les annonces trompeuses.</li>
        </ul>
      </>
    ),
  },
  {
    title: "Transactions et responsabilité",
    body: (
      <p>
        LeBon42 met en relation acheteurs et vendeurs mais n’est pas partie à la
        transaction : la vente se conclut directement entre les utilisateurs. Nous
        ne garantissons ni l’état des biens, ni le paiement, ni la livraison.
        Soyez prudent et privilégiez la remise en main propre sur le campus.
      </p>
    ),
  },
  {
    title: "Avis et notes",
    body: (
      <p>
        Les avis doivent être honnêtes et respectueux. Les avis faux, injurieux ou
        diffamatoires sont interdits et peuvent être supprimés.
      </p>
    ),
  },
  {
    title: "Modération et signalements",
    body: (
      <p>
        Tout utilisateur peut signaler un contenu. Les modérateurs et
        administrateurs peuvent masquer ou supprimer un contenu et bloquer un
        utilisateur, notamment en cas de manquement aux présentes conditions.
      </p>
    ),
  },
  {
    title: "Propriété intellectuelle",
    body: (
      <p>
        Vous conservez la propriété des contenus que vous publiez. En les
        publiant, vous accordez à LeBon42 une licence non exclusive d’affichage
        dans le cadre du service. Le nom, le logo et le code du projet restent la
        propriété de l’équipe.
      </p>
    ),
  },
  {
    title: "Comportements interdits",
    body: (
      <ul className="list-disc pl-5 space-y-1">
        <li>tenter de contourner la sécurité ou les limitations du service ;</li>
        <li>usurper l’identité d’une autre personne ;</li>
        <li>publier les données personnelles d’un tiers sans son accord ;</li>
        <li>harceler d’autres utilisateurs ;</li>
        <li>extraire automatiquement les données de la plateforme (scraping).</li>
      </ul>
    ),
  },
  {
    title: "Suspension et suppression",
    body: (
      <p>
        Nous pouvons suspendre ou supprimer un compte en cas de manquement aux
        présentes conditions. Vous pouvez demander la suppression de votre compte
        à tout moment.
      </p>
    ),
  },
  {
    title: "Limitation de responsabilité",
    body: (
      <p>
        Le service est fourni « en l’état ». LeBon42 ne peut être tenu responsable
        des dommages indirects, des pertes de données ou des transactions
        conclues entre utilisateurs.
      </p>
    ),
  },
  {
    title: "Droit applicable",
    body: (
      <p>
        Les présentes conditions sont régies par le droit français. En cas de
        litige, une solution amiable sera recherchée en priorité.
      </p>
    ),
  },
  {
    title: "Modifications",
    body: (
      <p>
        Ces conditions peuvent évoluer. La date de dernière mise à jour figure en
        haut de la page ; l’usage continu du service vaut acceptation.
      </p>
    ),
  },
  {
    title: "Contact",
    body: (
      <p>
        Pour toute question, contactez un admin de l’équipe LeBon42 via l’espace
        Messages de l’application ou le dépôt du projet.
      </p>
    ),
  },
];

export default function TermsPage() {
  return (
    <LegalPage
      title="Conditions d’utilisation"
      updatedAt={UPDATED_AT}
      sections={sections}
    />
  );
}
