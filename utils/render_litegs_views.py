import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image
import torch
from torch.utils.data import DataLoader


REPO_ROOT = Path(__file__).resolve().parents[1]
LITEGS_ROOT = REPO_ROOT / "LiteGS"
sys.path.insert(0, str(LITEGS_ROOT))

import litegs  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a trained LiteGS model from every COLMAP training camera "
            "view and save render/GT/comparison images plus per-view metrics."
        )
    )
    parser.add_argument(
        "-s",
        "--source_path",
        required=True,
        type=str,
        help="Scene source path, e.g. ./data/0615/2026-06-15-194903.",
    )
    parser.add_argument(
        "-m",
        "--model_path",
        required=True,
        type=str,
        help="LiteGS model directory, e.g. ./results/0615/194903.",
    )
    parser.add_argument(
        "-i",
        "--images",
        default="images",
        type=str,
        help="Image folder under source_path. Defaults to undistorted ./images.",
    )
    parser.add_argument(
        "-r",
        "--resolution",
        default=2,
        type=int,
        help="Same resolution/downsample used for training.",
    )
    parser.add_argument(
        "--sh_degree",
        default=3,
        type=int,
        help="Spherical harmonics degree used by the trained model.",
    )
    parser.add_argument(
        "--output_dir",
        default=None,
        type=str,
        help="Output directory. Defaults to <model_path>/train_view_renders.",
    )
    parser.add_argument(
        "--cluster_size",
        default=128,
        type=int,
        help="LiteGS cluster size. Keep this consistent with training.",
    )
    parser.add_argument(
        "--max_images",
        default=None,
        type=int,
        help="Optional limit for quick checks.",
    )
    return parser.parse_args()


def tensor_to_uint8_image(image: torch.Tensor) -> np.ndarray:
    array = image.detach().clamp(0.0, 1.0).cpu()[0].permute(1, 2, 0).numpy()
    return (array * 255.0 + 0.5).astype(np.uint8)


def save_rgb(path: Path, image: np.ndarray) -> None:
    Image.fromarray(image).save(path)


def psnr_value(render: torch.Tensor, gt: torch.Tensor) -> float:
    mse = torch.mean((render - gt) ** 2)
    if mse <= 0:
        return float("inf")
    return float((-10.0 * torch.log10(mse)).detach().cpu())


def mae_value(render: torch.Tensor, gt: torch.Tensor) -> float:
    return float(torch.mean(torch.abs(render - gt)).detach().cpu())


def load_scene(args: argparse.Namespace):
    source_path = Path(args.source_path).resolve()
    model_path = Path(args.model_path).resolve()
    ply_path = model_path / "point_cloud" / "finish" / "point_cloud.ply"

    if not source_path.exists():
        raise FileNotFoundError(f"Source path does not exist: {source_path}")
    if not ply_path.exists():
        raise FileNotFoundError(f"Trained PLY not found: {ply_path}")

    cameras_info, camera_frames, _, _ = litegs.io_manager.load_colmap_result(
        str(source_path),
        args.images,
    )
    for camera_frame in camera_frames:
        camera_frame.load_image(args.resolution)

    dataset = litegs.data.CameraFrameDataset(
        cameras_info,
        camera_frames,
        args.resolution,
        True,
    )

    xyz, scale, rot, sh_0, sh_rest, opacity = litegs.io_manager.load_ply(
        str(ply_path),
        args.sh_degree,
    )
    tensors = [
        torch.tensor(value, dtype=torch.float32, device="cuda")
        for value in (xyz, scale, rot, sh_0, sh_rest, opacity)
    ]
    return model_path, dataset, tensors


def prepare_model(tensors, cluster_size: int):
    xyz, scale, rot, sh_0, sh_rest, opacity = tensors
    cluster_origin = None
    cluster_extend = None

    if cluster_size > 0:
        xyz, scale, rot, sh_0, sh_rest, opacity = litegs.scene.point.spatial_refine(
            False,
            None,
            xyz,
            scale,
            rot,
            sh_0,
            sh_rest,
            opacity,
        )
        xyz, scale, rot, sh_0, sh_rest, opacity = litegs.scene.cluster.cluster_points(
            cluster_size,
            xyz,
            scale,
            rot,
            sh_0,
            sh_rest,
            opacity,
        )
        cluster_origin, cluster_extend = litegs.scene.cluster.get_cluster_AABB(
            xyz,
            scale.exp(),
            torch.nn.functional.normalize(rot, dim=0),
        )

    return cluster_origin, cluster_extend, (xyz, scale, rot, sh_0, sh_rest, opacity)


def main() -> int:
    args = parse_args()
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else Path(args.model_path).resolve() / "train_view_renders"
    )
    render_dir = output_dir / "render"
    gt_dir = output_dir / "gt"
    compare_dir = output_dir / "compare"

    try:
        for directory in (render_dir, gt_dir, compare_dir):
            directory.mkdir(parents=True, exist_ok=True)

        model_path, dataset, tensors = load_scene(args)
        cluster_origin, cluster_extend, tensors = prepare_model(
            tensors,
            args.cluster_size,
        )
        xyz, scale, rot, sh_0, sh_rest, opacity = tensors

        loader = DataLoader(dataset, batch_size=1, shuffle=False, pin_memory=False)
        rows = []

        with torch.no_grad():
            for index, (view_matrix, proj_matrix, frustumplane, gt_image, idx) in enumerate(loader):
                if args.max_images is not None and index >= args.max_images:
                    break

                view_matrix = view_matrix.cuda()
                proj_matrix = proj_matrix.cuda()
                frustumplane = frustumplane.cuda()
                gt_image = gt_image.cuda() / 255.0

                (
                    _visible_chunkid,
                    _visible_chunks_num,
                    culled_xyz,
                    culled_scale,
                    culled_rot,
                    culled_color,
                    culled_opacity,
                ) = litegs.render.render_preprocess(
                    cluster_origin,
                    cluster_extend,
                    frustumplane,
                    view_matrix,
                    xyz,
                    scale,
                    rot,
                    sh_0,
                    sh_rest,
                    opacity,
                    None,
                    None,
                    argparse.Namespace(
                        cluster_size=args.cluster_size,
                        tile_size=(8, 16),
                        sparse_grad=True,
                        device_preload=True,
                        enable_transmitance=False,
                        enable_depth=False,
                        input_color_type="sh",
                    ),
                    args.sh_degree,
                )
                render_image, _transmitance, _depth, _normal, _primitive_visible = (
                    litegs.render.render(
                        view_matrix,
                        proj_matrix,
                        culled_xyz,
                        culled_scale,
                        culled_rot,
                        culled_color,
                        culled_opacity,
                        None,
                        None,
                        None,
                        args.sh_degree,
                        gt_image.shape[2:],
                        argparse.Namespace(
                            tile_size=(8, 16),
                            sparse_grad=True,
                            enable_transmitance=False,
                            enable_depth=False,
                        ),
                    )
                )

                frame = dataset.frames[int(idx.item())]
                stem = Path(frame.name).stem
                psnr = psnr_value(render_image, gt_image)
                mae = mae_value(render_image, gt_image)

                render_np = tensor_to_uint8_image(render_image)
                gt_np = tensor_to_uint8_image(gt_image)
                compare_np = np.concatenate([gt_np, render_np], axis=1)

                save_rgb(gt_dir / f"{stem}.png", gt_np)
                save_rgb(render_dir / f"{stem}.png", render_np)
                save_rgb(compare_dir / f"{stem}_gt_render.png", compare_np)

                rows.append(
                    {
                        "index": index,
                        "image_name": frame.name,
                        "camera_id": frame.camera_id,
                        "psnr": psnr,
                        "mae": mae,
                    }
                )
                print(f"{index + 1:03d}/{len(dataset):03d} {frame.name} PSNR={psnr:.3f} MAE={mae:.6f}")

        csv_path = output_dir / "metrics.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["index", "image_name", "camera_id", "psnr", "mae"],
            )
            writer.writeheader()
            writer.writerows(rows)

        if rows:
            mean_psnr = sum(row["psnr"] for row in rows) / len(rows)
            mean_mae = sum(row["mae"] for row in rows) / len(rows)
            print(f"Rendered {len(rows)} views for {model_path}")
            print(f"Mean PSNR={mean_psnr:.3f}, Mean MAE={mean_mae:.6f}")
        print(f"Output: {output_dir}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
