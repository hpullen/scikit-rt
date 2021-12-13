"""Classes for creating synthetic images with simple geometries."""

import os
import numpy as np
import nibabel
import shutil
from scipy import ndimage

from skrt.image import Image, _axes
from skrt.structures import StructureSet, ROI
import skrt.core


class SyntheticImage(Image):
    """Class for creating synthetic image data with simple geometric shapes."""

    def __init__(
        self,
        shape,
        filename=None,
        origin=(0, 0, 0),
        voxel_size=(1, 1, 1),
        intensity=-1024,
        noise_std=None,
    ):
        """Create an initially blank synthetic image to which geometric 
        ROIs can be added.

        **Parameters:**
        
        shape : int/tuple
            Dimensions of the image array to create in order (x, y, z).
            If an int is given, the image will be created with dimensions
            (shape, shape, shape).

        filename : str, default=None
            Name of output file or directory. If given, the file will
            automatically be written; otherwise, no file will be written until
            the 'write' method is called.

        origin : tuple, default=(0, 0, 0)
            Origin in mm for the image in order (x, y, z).

        voxel_size : tuple, default=(1, 1, 1)
            Voxel sizes in mm for the image in order (x, y, z).

        intensity : float, default=-1000
            Intensity in HU for the background of the image.

        noise_std : float, default=None
            Standard deviation of Gaussian noise to apply to the image.
            If None, no noise will be applied.
        """

        # Assign properties
        shape = skrt.core.to_list(shape)
        self.shape = [shape[1], shape[0], shape[2]]
        self.voxel_size = [abs(v) for v in skrt.core.to_list(voxel_size)]
        self.origin = origin
        self.max_hu = 0 if noise_std is None else noise_std * 3
        self.min_hu = -self.max_hu if self.max_hu != 0 else -20
        self.noise_std = noise_std
        self.bg_intensity = intensity
        self.shapes = []
        self.roi_shapes = {}
        self.rois = {}
        self.groups = {}
        self.shape_count = {}
        self.translation = None
        self.rotation = None

        # Initialise as Image
        Image.__init__(
            self, self.get_background(), voxel_size=self.voxel_size,
            origin=self.origin
        )

        # Write to file if a filename is given
        if filename is not None:
            self.filename = os.path.expanduser(filename)
            self.write()

    def view(self, **kwargs):
        """View with QuickViewer."""

        from skrt.viewer import QuickViewer

        qv_kwargs = {
            "hu": [self.min_hu, self.max_hu],
            "title": "",
            "origin": self.origin,
            "voxel_size": self.voxel_size,
            "mpl_kwargs": {"interpolation": "none"},
        }
        qv_kwargs.update(kwargs)
        rois = self.get_roi_data()
        QuickViewer(self.get_data(), structs=rois, **qv_kwargs)

    def update(self, force_bkg=False):
        """Update self.data so that it contains all current shapes."""

        # Get background array
        data = self.get_background(with_noise=False).copy()

        # Add shapes
        for shape in self.shapes:
            data[shape.get_data(self.get_coords())] = shape.intensity

        # Apply noise
        data = self.apply_noise(data)
        self.data = data

        # Assign structure set
        self.clear_structure_sets()
        self.add_structure_set(self.get_structure_set())

    def get_image(self):
        """Get self as an Image object."""

        self.update()
        return Image(self)

    def get_data(self, **kwargs):
        """Get Image data."""

        self.update()
        return Image.get_data(self, **kwargs)

    def plot(self, **kwargs):
        """Plot the current image with ROIs overlaid."""

        self.update()
        self.update_rois()
        kwargs.setdefault("rois", -1)
        Image.plot(self, **kwargs)

    def view(self, **kwargs):
        """View the current image with QuickViewer."""

        from skrt.better_viewer import BetterViewer
        kwargs.setdefault("rois", self.get_structure_set())
        return BetterViewer(self.get_image(), **kwargs)

    def get_roi_data(self):
        """Get dict of ROIs and names with any transformations applied."""

        roi_data = {}
        for name, shape in self.roi_shapes.items():
            data = shape.get_data(self.get_coords())
            roi_data[name] = data
        return roi_data

    def get_structure_set(self):
        """Return StructureSet containing own structures."""

        self.update_rois()
        return StructureSet(list(self.rois.values()))

    def update_roi(self, name):
        """Update an ROI to ensure it has the correct data."""
        
        self.rois[name].data = self.roi_shapes[name].get_data(self.get_coords())

    def update_rois(self):
        """Update all ROIs to have the correct data."""

        for name in self.rois:
            self.update_roi(name)

    def get_roi(self, name):
        """Get a named ROI as an ROI object."""

        if name not in self.rois:
            print("ROI", name, "not found!")
            return

        self.update_roi(name)
        return self.rois[name]

    def get_rois(self):
        """Get list of all owned ROI objects."""

        self.update_rois()
        return list(self.rois.values())

    def write(self, outname=None, overwrite_roi_dir=False):
        """Write image data to an output file."""

        # Check filename
        if outname is None:
            if hasattr(self, "filename"):
                outname = self.filename
            else:
                raise RuntimeError(
                    "Filename must be specified in __init__() " "or write()!"
                )

        # Write image data
        self.update()
        Image.write(self, outname)

        # Write ROIs
        structure_set = self.get_structure_set()
        exts = [".nii", ".nii.gz", ".npy"]
        outdir = outname
        ext_to_use = None
        for ext in exts:
            if outname.endswith(ext):
                ext_to_use = ext
                outdir = outname.replace(ext, "")
        structure_set.write(outdir=outdir, ext=ext_to_use, 
                            overwrite=overwrite_roi_dir)

    def get_background(self, with_noise=True, force=False):
        """Make blank image array or noisy array."""

        bkg = np.ones(self.shape) * self.bg_intensity
        if with_noise:
            bkg = self.apply_noise(bkg)
        return bkg

    def apply_noise(self, array):
        """Apply background noise to an array."""

        if self.noise_std is not None:
            array += np.random.normal(0, self.noise_std, array.shape)
        return array

    def set_noise_std(self, std):

        self.noise_std = std
        self.update(force_bkg=True)

    def reset(self):
        """Remove all shapes."""

        self.shapes = []
        self.roi_shapes = {}
        self.groups = {}
        self.shape_count = {}
        self.translation = None
        self.rotation = None
        self.update()

    def add_shape(self, shape, shape_type, is_roi, above, group):

        if above:
            self.shapes.append(shape)
        else:
            self.shapes.insert(0, shape)

        # Automatically treat as ROI if given a group or name
        if is_roi is None and (group is not None or shape.name is not None):
            is_roi = True

        if is_roi:
            if group is not None:
                if group not in self.groups:
                    self.groups[group] = ShapeGroup([shape], name=group)
                    self.roi_shapes[group] = self.groups[group]
                    self.rois[group] = ROI(
                        shape.get_data(self.get_coords()), name=group, 
                        affine=self.get_affine()
                    )
                else:
                    self.groups[group].add_shape(shape)
            else:

                if shape_type not in self.shape_count:
                    self.shape_count[shape_type] = 1
                else:
                    self.shape_count[shape_type] += 1

                if shape.name is None:
                    shape.name = f"{shape_type}{self.shape_count[shape_type]}"

                self.roi_shapes[shape.name] = shape
                self.rois[shape.name] = ROI(
                    shape.get_data(self.get_coords()), name=shape.name, 
                    affine=self.get_affine()
                )

        self.min_hu = min([shape.intensity, self.min_hu])
        self.max_hu = max([shape.intensity, self.max_hu])
        if is_roi:
            return self.rois[shape.name]

    def add_sphere(
        self,
        radius,
        centre=None,
        intensity=0,
        is_roi=None,
        name=None,
        above=True,
        group=None,
    ):

        if centre is None:
            centre = self.get_centre()
        sphere = Sphere(self.shape, radius, centre, intensity, name)
        return self.add_shape(sphere, "sphere", is_roi, above, group)

    def add_cylinder(
        self,
        radius,
        length,
        axis="z",
        centre=None,
        intensity=0,
        is_roi=None,
        name=None,
        above=True,
        group=None,
    ):

        if centre is None:
            centre = self.get_centre()
        cylinder = Cylinder(self.shape, radius, length, axis, centre, intensity, name)
        return self.add_shape(cylinder, "cylinder", is_roi, above, group)

    def add_cube(
        self,
        side_length,
        centre=None,
        intensity=0,
        is_roi=None,
        name=None,
        above=True,
        group=None,
    ):

        return self.add_cuboid(
            side_length, centre, intensity, is_roi, name, above, group=group
        )

    def add_cuboid(
        self,
        side_length,
        centre=None,
        intensity=0,
        is_roi=None,
        name=None,
        above=True,
        group=None,
    ):

        if centre is None:
            centre = self.get_centre()
        side_length = skrt.core.to_list(side_length)

        cuboid = Cuboid(self.shape, side_length, centre, intensity, name)
        return self.add_shape(cuboid, "cuboid", is_roi, above, group)

    def add_grid(
        self, spacing, thickness=1, intensity=0, axis=None, name=None, above=True,
    ):

        grid = Grid(self.shape, spacing, thickness, intensity, axis, name)
        self.add_shape(grid, "grid", False, above, group=None)

    def reset_transforms(self):
        """Remove any rotations or translations."""

        self.translation = None
        self.rotation = None
        for shape in self.shapes:
            shape.translation = None
            shape.rotation = None

    def translate(self, dx=0, dy=0, dz=0):
        """Set a translation to apply to the final image."""

        self.translation = (dy, dx, dz)

    def rotate(self, yaw=0, pitch=0, roll=0):
        """Set a rotation to apply to the final image."""

        self.rotation = (yaw, pitch, roll)


class ShapeGroup:
    def __init__(self, shapes, name):

        self.name = name
        self.shapes = shapes

    def add_shape(self, shape):
        self.shapes.append(shape)

    def get_data(self, coords):

        data = self.shapes[0].get_data(coords)
        for shape in self.shapes[1:]:
            data += shape.get_data(coords)
        return data


class Sphere:
    def __init__(self, shape, radius, centre, intensity, name=None):

        self.name = name
        self.radius = radius
        self.centre = centre
        self.intensity = intensity

    def get_data(self, coords):

        distance_to_centre = np.sqrt(
            (coords[1] - self.centre[1]) ** 2
            + (coords[0] - self.centre[0]) ** 2
            + (coords[2] - self.centre[2]) ** 2
        )
        return distance_to_centre <= self.radius


class Cuboid:
    def __init__(self, shape, side_length, centre, intensity, name=None):

        self.name = name
        self.side_length = skrt.core.to_list(side_length)
        self.centre = centre
        self.intensity = intensity

    def get_data(self, coords):

        try:
            data = (
                (np.absolute(coords[1] - self.centre[1]) <= self.side_length[1] / 2)
                & (np.absolute(coords[0] - self.centre[0]) <= self.side_length[0] / 2)
                & (np.absolute(coords[2] - self.centre[2]) <= self.side_length[2] / 2)
            )
            return data
        except TypeError:
            print("centre:", self.centre)
            print("side length:", self.side_length)


class Cylinder:
    def __init__(self, shape, radius, length, axis, centre, intensity, name=None):

        self.radius = radius
        self.length = length
        self.centre = centre
        self.axis = axis
        self.intensity = intensity
        self.name = name

    def get_data(self, coords):

        # Get coordinates in each direction
        axis_idx = _axes.index(self.axis)
        circle_idx = [i for i in range(3) if i != axis_idx]
        coords_c1 = coords[circle_idx[1]]
        coords_c2 = coords[circle_idx[0]]
        coords_length = coords[axis_idx]

        # Get centre in each direction
        centre = [self.centre[1], self.centre[0], self.centre[2]]
        centre_c1 = centre[circle_idx[1]]
        centre_c2 = centre[circle_idx[0]]
        centre_length = centre[axis_idx]

        # Make cylinder array
        data = (
            np.sqrt((coords_c1 - centre_c1) ** 2 + (coords_c2 - centre_c2) ** 2)
            <= self.radius
        ) & (np.absolute(coords_length - centre_length) <= self.length / 2)
        return data


class Grid:
    def __init__(self, shape, spacing, thickness, intensity, axis=None, name=None):

        self.name = name
        self.spacing = skrt.core.to_list(spacing)
        self.thickness = skrt.core.to_list(thickness)
        self.intensity = intensity
        self.axis = axis
        self.shape = shape

    def get_data(self, _):

        coords = np.meshgrid(
            np.arange(0, self.shape[1]),
            np.arange(0, self.shape[0]),
            np.arange(0, self.shape[2]),
        )
        if self.axis is not None:
            axis = _axes.index(self.axis)
            ax1, ax2 = [i for i in [0, 1, 2] if i != axis]
            return (coords[ax1] % self.spacing[ax1] < self.thickness[ax1]) | (
                coords[ax2] % self.spacing[ax2] < self.thickness[ax2]
            )
        else:
            return (
                (coords[1] % self.spacing[1] < self.thickness[1])
                | (coords[0] % self.spacing[0] < self.thickness[0])
                | (coords[2] % self.spacing[2] < self.thickness[2])
            )
