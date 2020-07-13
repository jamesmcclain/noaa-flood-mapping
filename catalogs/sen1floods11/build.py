from datetime import datetime
import json
import os

import click
from pystac import (
    Asset,
    Catalog,
    CatalogType,
    Collection,
    Extensions,
    Extent,
    Item,
    Link,
    LinkType,
    SpatialExtent,
    TemporalExtent,
)
from pystac.extensions.label import LabelClasses, LabelType
import rasterio
from shapely.geometry import GeometryCollection, box, shape

from storage.cloud_storage import GoogleCloudStorage


def image_date_for_country(sentinel_version, country):
    """ Returns Datetime for country from metadata or None if no result """
    cnn_chips_geojson_file = "./data/CNN_Chips_FTC.geojson"
    GoogleCloudStorage("cnn_chips").download(
        os.path.basename(cnn_chips_geojson_file), cnn_chips_geojson_file
    )
    f = open(cnn_chips_geojson_file)
    chip_metadata = json.load(f)
    f.close()
    metadata = next(
        (x for x in chip_metadata["features"] if x["id"].startswith(country)), None,
    )
    if metadata is not None:
        date_field = "{}_date".format(sentinel_version.lower())
        return datetime.strptime(metadata["properties"][date_field], "%Y-%m-%d")
    else:
        return None


def collection_update_extents(collection):
    bounds = GeometryCollection(
        [shape(s.geometry) for s in collection.get_all_items()]
    ).bounds
    collection.extent.spatial = SpatialExtent(bounds)

    t_min = min([i.datetime for i in collection.get_all_items()])
    t_max = max([i.datetime for i in collection.get_all_items()])
    if t_min == t_max:
        collection.extent.temporal = TemporalExtent([(t_min, None)])
    else:
        collection.extent.temporal = TemporalExtent([(t_min, t_max)])


def collection_add_sentinel_chips(collection, uri_list, sentinel_version):
    """ Add sentinel images to a collection """
    for uri in uri_list:

        if not uri.endswith(".tif"):
            continue

        item_id = os.path.basename(uri).split(".")[0]
        country, *_ = item_id.split("_")
        params = {}
        params["id"] = item_id
        params["collection"] = collection
        params["properties"] = {}

        # Get or Create sub catalog for event country
        country_catalog_id = "{}-{}".format(sentinel_version.upper(), country)
        country_catalog = collection.get_child(country_catalog_id, recursive=False)
        if country_catalog is None:
            country_catalog = Catalog(
                country_catalog_id, "Flood Chips in {}".format(country)
            )
            print("Add STAC Catalog {}".format(country_catalog.id))
            collection.add_child(country_catalog)

        with rasterio.open("/vsicurl/{}".format(uri)) as src:
            params["bbox"] = list(src.bounds)
            params["geometry"] = box(*params["bbox"]).__geo_interface__

        params["datetime"] = image_date_for_country(sentinel_version, country)

        # Create Tiff Item
        item = Item(**params)
        asset = Asset(
            href=uri, title="GeoTiff", media_type="image/tiff; application=geotiff"
        )
        item.add_asset(key="image", asset=asset)
        country_catalog.add_item(item)
        print("Added STAC Item {}".format(item.id))


def label_collection_add_items(
    collection,
    root_catalog,
    uri_list,
    links_func,
    label_description,
    label_type,
    label_classes=None,
    label_tasks=None,
):
    """ Add uri_list tif uris to collection as LabelItems

    root_catalog is the top level node in the STAC Catalog where the chips labeled by these tifs
    can be found. Required to correctly setup Links to the source chips.

    links_func is a method with the following signature:
        def links_func(root_catalog: Catalog,
                       label_item: LabelItem,
                       country: str,
                       event_id: int): [Link]
    This method should construct a list of links that map the label_item to the STAC objects in
    the root_catalog that label_item is derived from.

    The label_ arguments will be passed down to each LabelItem in the collection

    """
    for uri in uri_list:
        if not uri.endswith(".tif"):
            continue

        item_id = os.path.basename(uri).split(".")[0]
        country, event_id, *_ = item_id.split("_")

        # Get or Create sub catalog for event country
        country_catalog_id = "{}-{}".format(collection.id, country)
        country_catalog = collection.get_child(country_catalog_id, recursive=False)
        if country_catalog is None:
            country_catalog = Catalog(
                country_catalog_id, "Flood Chips in {}".format(country)
            )
            print("Add STAC Catalog {}".format(country_catalog.id))
            collection.add_child(country_catalog)

        params = {}
        params["id"] = item_id
        params["collection"] = collection
        params["datetime"] = image_date_for_country("s1", country)
        params["stac_extensions"] = [Extensions.LABEL]
        params["properties"] = {}
        with rasterio.open("/vsicurl/{}".format(uri)) as src:
            params["bbox"] = list(src.bounds)
            params["geometry"] = box(*params["bbox"]).__geo_interface__

        label_ext_params = {}
        if isinstance(label_classes, list):
            label_ext_params["label_classes"] = label_classes
        else:
            label_ext_params["label_classes"] = []
        label_ext_params["label_description"] = label_description
        if label_tasks is not None:
            label_ext_params["label_tasks"] = label_tasks
        label_ext_params["label_type"] = label_type

        item = Item(**params)
        item.ext.label.apply(**label_ext_params)
        item.links = links_func(root_catalog, item, country, event_id)

        # Add Asset
        asset = Asset(
            href=uri, title="GeoTiff", media_type="image/tiff; application=geotiff"
        )
        item.add_asset(key="image", asset=asset)

        country_catalog.add_item(item)
        print("Added STAC Item {}".format(item.id))


def sentinel1_links_func(root_catalog, label_item, country, event_id):
    """ links_func that looks up country + event id in only S1 """
    return [
        Link(
            "derived_from",
            o,
            link_type=LinkType.RELATIVE,
            media_type="image/tiff; application=geotiff",
        ).set_owner(label_item)
        for o in [
            root_catalog.get_item("{}_{}_S1".format(country, event_id), recursive=True),
        ]
        if o is not None
    ]


def sentinel1_sentinel2_links_func(root_catalog, label_item, country, event_id):
    """ links_func that looks up country + event id in both S1 and S2 """
    return [
        Link(
            "derived_from",
            o,
            link_type=LinkType.RELATIVE,
            media_type="image/tiff; application=geotiff",
        ).set_owner(label_item)
        for o in [
            root_catalog.get_item("{}_{}_S1".format(country, event_id), recursive=True),
            root_catalog.get_item("{}_{}_S2".format(country, event_id), recursive=True),
        ]
        if o is not None
    ]


@click.command(help="Build STAC Catalog for sen1floods11")
def main():
    """

# The Data

446 qc'ed chips containing flood events, hand-labeled flood classifications
4385 non-qc'ed chips containing water exported only with sentinel 1 and 2 flood classifications

hand-labeled chips listed in CNN_Chips_FTC.geojson

- NoQC: 4385 tifs ???
- Perm: 446 tifs of JRC data in PermJRC resampled to chips matching hand labeled classifications
- PermJRC: tifs of JRC permanent water classifications
- QC_v2: 446 tifs of hand labeled chips flood classifications
- S1: 446 Sentinel 1 tifs resampled to chips matching hand labeled classifications
- S1_NoQC: 4385 Sentinel 1 tifs resampled to chips
- S1Flood: 446 tifs of flood classification computed via Otsu threshold (traditional) algorithm
           available for hand-labeled chip
- S1Flood_NoQC: 4385 tifs of flood classification computed via automated "weak" algorithm
- S2: Sentinel 2 tifs resampled to chips matching hand labeled classifications
- S2Flood: 7 tifs of flood classification computed via Otsu threshold (traditional) algorithm
           available for hand-labeled chips
- S2_NoQC: 4385 Sentinel 2 tifs resampled to chips

# The Catalog Outline

** We want to generate a root catalog that is all, or only training, or only validation items **
^^^ Script should support this

- Root Catalog
    - Collection: Sentinel 1 data chips
        - Catalog: Event (Country)
            - Item: The Item
    - Collection: Sentinel 2 data chips
        - Catalog: Event (Country)
            - Item: The Item
    - Collection: JRC Raw data
        - Catalog: Lat bucket
            - Catalog: Lon bucket
                - Item: The Item
    - Collection: Sentinel 1 weak labels
        - Catalog: Event (Country)
            - Item: The Item
    - Collection: Hand labels
        - Catalog: Event (Country)
            - Item: The Item
    - Collection: Permanent water labels
        - Catalog: Event (Country)
            - Item: The Item
    - Collection: Traditional otsu algo labels
        - Catalog: Event (Country)
            - Item: The Item

## Alternate catalog structure

This structure was considered but rejected in the interest of facilitating collections for each
of the label datasets.

- Root Catalog
    - Collection: Sentinel 1
        - Catalog: Country
            - Catalog: Event ID
                (Note: Catalog will always have the first item. Then it will either have the second
                       item or all the others depending on which dir the first item came from)
                - Item: (dir: S1 + S1_NoQC) Sentinel 1 data chip
                - Item: (dir: S1Flood_NoQC) Labels from "weak" classification algorithm applied to S1
                - Item: (dir: QC_v2) Labels from hand classification (ORed with item below)
                - Item: (dir: S1Flood) Labels from traditional Otsu algorithm
                - Item: (dir: Perm) Labels from perm water dataset (this is a Byte tiff, only 1 or 0
                        for yes or no perm water)
    - Collection: Sentinel 2
        - Catalog: Country
            - Catalog: Event ID
                - Item: (dir: S2 + S2_NoQC) Sentinel 2 data chip
                - Item: (dir: S2Flood) Labels from traditional Otsu algorithm applied to S2
    - Collection: PermJRC
        - Catalog: Lat 10
            - Catalog: Lon 10
                - Item: (dir: PermJRC)


    """
    storage = GoogleCloudStorage("cnn_chips")

    catalog_description = "Bonafilia, D., Tellman, B., Anderson, T., Issenberg, E. 2020. Sen1Floods11: a georeferenced dataset to train and test deep learning flood algorithms for Sentinel-1. The IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR) Workshops, 2020, pp. 210-211. Available Open access at: http://openaccess.thecvf.com/content_CVPRW_2020/html/w11/Bonafilia_Sen1Floods11_A_Georeferenced_Dataset_to_Train_and_Test_Deep_Learning_CVPRW_2020_paper.html"  # noqa: E501
    catalog_title = "A georeferenced dataset to train and test deep learning flood algorithms for Sentinel-1"  # noqa: E501

    catalog = Catalog("sen1floods11", catalog_description, title=catalog_title)
    print("Created Catalog {}".format(catalog.id))

    # Build Sentinel 1 Collection
    sentinel1 = Collection(
        "Sentinel1",
        "Raw Sentinel-1 imagery. IW mode, GRD product. See https://developers.google.com/earth-engine/sentinel1 for information on preprocessing",  # noqa: E501
        extent=Extent(SpatialExtent([None, None, None, None]), None),
    )
    print("Created STAC Collection: {}".format(sentinel1.id))
    collection_add_sentinel_chips(sentinel1, list(storage.ls("S1/"))[:2], "s1")
    collection_add_sentinel_chips(sentinel1, list(storage.ls("S1_NoQC/"))[:2], "s1")
    collection_update_extents(sentinel1)
    catalog.add_child(sentinel1)

    # Build Sentinel 2 Collection
    sentinel2 = Collection(
        "Sentinel2",
        "Raw Sentinel-2 MSI Level-1C imagery. Contains all spectral bands (1 - 12). Does not contain QA mask.",  # noqa: E501
        extent=Extent(SpatialExtent([None, None, None, None]), None),
    )
    print("Created STAC Collection: {}".format(sentinel2.id))
    collection_add_sentinel_chips(sentinel2, list(storage.ls("S2/"))[:2], "s2")
    collection_add_sentinel_chips(sentinel2, list(storage.ls("S2_NoQC/"))[:2], "s2")
    collection_update_extents(sentinel2)
    catalog.add_child(sentinel2)

    # Build S1 Weak Labels Collection
    s1weak_labels = Collection(
        "S1WeakLabels",
        "A weakly supervised training dataset using Sentinel-1 based flood classifications as labels",  # noqa: E501
        extent=Extent(SpatialExtent([None, None, None, None]), None),
        stac_extensions=[Extensions.LABEL],
    )
    label_collection_add_items(
        s1weak_labels,
        catalog,
        list(storage.ls("S1Flood_NoQC/"))[:2],
        sentinel1_links_func,
        "-1: No Data / Not Valid. 0: Not Water. 1: Water.",  # noqa: E501
        LabelType.RASTER,
        label_classes=[LabelClasses([-1, 0, 1])],
        label_tasks=["classification"],
    )
    collection_update_extents(s1weak_labels)
    catalog.add_child(s1weak_labels)

    # Build Hand Labels Collection
    hand_labels = Collection(
        "HandLabels",
        "Hand labeled chips of surface water from selected flood events",
        extent=Extent(SpatialExtent([None, None, None, None]), None),
        stac_extensions=[Extensions.LABEL],
    )
    label_collection_add_items(
        hand_labels,
        catalog,
        list(storage.ls("QC_v2/"))[:2],
        sentinel1_sentinel2_links_func,
        "Hand labeled chips containing ground truth. -1: No Data / Not Valid. 0: Not Water. 1: Water.",  # noqa: E501
        LabelType.RASTER,
        label_classes=[LabelClasses([-1, 0, 1])],
        label_tasks=["classification"],
    )
    collection_update_extents(hand_labels)
    catalog.add_child(hand_labels)

    # Build Permanent Labels collection
    permanent_labels = Collection(
        "PermanentLabels",
        "Permanent water chips generated from the 'transition' layer of the JRC (European Commission Joint Research Centre) dataset",  # noqa: E501
        extent=Extent(SpatialExtent([None, None, None, None]), None),
        stac_extensions=[Extensions.LABEL],
    )
    label_collection_add_items(
        permanent_labels,
        catalog,
        list(storage.ls("Perm/"))[:2],
        lambda *_: [],  # No easy way to map JRC source files to the label chips...
        "0: Not Water. 1: Water.",
        LabelType.RASTER,
        label_classes=[LabelClasses([0, 1])],
        label_tasks=["classification"],
    )
    collection_update_extents(permanent_labels)
    catalog.add_child(permanent_labels)

    # Build Otsu algorithm Labels collection
    otsu_labels = Collection(
        "TraditionalLabels",
        "Water labels generated via traditional Otsu’s thresholding algorithm on the Sentinel 1 VH band",  # noqa: E501
        extent=Extent(SpatialExtent([None, None, None, None]), None),
        stac_extensions=[Extensions.LABEL],
    )
    label_collection_add_items(
        otsu_labels,
        catalog,
        list(storage.ls("S1Flood/"))[:2],
        sentinel1_links_func,
        "-1: No Data / Not Valid. 0: Not Water. 1: Water.",
        LabelType.RASTER,
        label_classes=[LabelClasses([-1, 0, 1])],
        label_tasks=["classification"],
    )
    collection_update_extents(otsu_labels)
    catalog.add_child(otsu_labels)

    # Save Complete Catalog
    root_path = "./catalog"
    catalog.normalize_and_save(root_path, catalog_type=CatalogType.SELF_CONTAINED)
    print("Saved STAC Catalog {} to {}...".format(catalog.id, root_path))


if __name__ == "__main__":
    main()
