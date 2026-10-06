import ProfilPage from "../page";

interface PageProps {
  params: Promise<{
    public_id: string;
  }>;
}

export default async function UserProfilePage(props: PageProps) {
  const { public_id } = await props.params;
  return <ProfilPage profileId={public_id} />;
}
