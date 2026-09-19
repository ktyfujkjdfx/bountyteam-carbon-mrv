# Retrieval fixture

`retrieval_cache/` is a real cache produced by `rs.case2.retrieve` against Earth
Search on 19 September 2026: one STAC search response and one 48x48 window of
band B8A from item `S2A_38ULF_20210712_1_L2A`, 4 KB of raster.

It exists so that offline replay can be tested without a network, including in
CI. It is **not** a scientific source and no analysis reads it. Every number in
this package comes from `data/`, the set supplied by the organizers; this fixture
is only used to prove that a cached retrieval can be replayed and that a cache
miss with the network disabled is an error rather than a silent local read.

The window is also what the compatibility check compares against the supplied
crop of the same scene: our scaling of the open product reproduces the supplied
values to 1.5e-8, which is float32 rounding.

Attribution: contains modified Copernicus Sentinel data 2021, accessed via
Element 84 Earth Search. Licence:
https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice
