import { Avatar } from "./Avatar";

export function PersonAvatar({
  photo,
  seed,
  name,
  size = 44,
}: {
  photo?: string;
  seed: string;
  name: string;
  size?: number;
}) {
  if (!photo) return <Avatar seed={seed} size={size} />;

  return (
    <img
      src={photo}
      alt={`${name}'s profile`}
      width={size}
      height={size}
      className="shrink-0 rounded-full object-cover ring-2 ring-peach/60"
      style={{ width: size, height: size }}
    />
  );
}
