# Native image geometry

`native_image_geometry.py` provides numeric PNG crop bounds and a PDF render plan. The module has no application caller and performs no object fetch, image decode, document open or page render. It accepts numeric geometry rather than native source objects. Source authorization, provenance and resource enforcement remain outside the planner.

## Input validation

Regions are exact four-element tuples of built-in integers or floats. Booleans, numeric subclasses, coercible objects and nonfinite values are rejected. A region contains normalized x, y, width and height. Width and height must be positive, and the region must fit within the unit square.

PDF crop and display-list bounds are exact four-element tuples. Coordinates must be finite, have absolute values no greater than one million, and form a positive rectangle. These checks constrain numeric inputs. They do not prove that the supplied bounds came from an authorized document or limit decoded resource use.

## PNG crop bounds

`png_crop_bounds` requires built-in integer dimensions between 1 and `2**31 - 1`. It floors the left and top coordinates, ceils the right and bottom coordinates, and clamps the bounds to the supplied dimensions. An empty result fails.

The calculation uses a private Decimal context with fixed precision, rounding and traps. Ambient Decimal configuration does not change its behavior. The function returns integer bounds and allocates no pixel buffer. Accepted dimensions therefore do not establish a safe decode or memory budget.

## PDF render plan

`pdf_render_plan` receives cropbox bounds, display-list bounds and a normalized region. The caller derives those values from the actual document. The planner does not inspect page rotation, crop metadata, UserUnit, annotations or transparency itself.

The planner clips the region to the cropbox. It rejects an empty clip or either clip dimension below 0.5. It then uses native MuPDF rectangle intersection, transformation and rounding to compute the first raster bounding box at 150 DPI.

If the first box's longest side is at most 1280 pixels, the plan returns that box and `dpi=150`, with no custom matrix. Otherwise, it scales the initial matrix by `1280 / longest_side` and computes the final box through the same native operations. Native rounding determines the final box. The calculation supplies no allocation, decode-time or render-time resource enforcement.

The frozen `PdfRenderPlan` contains the clip, first and final integer boxes, and either a matrix or a DPI value. It contains no document, pixmap, image bytes or source authority.

## Engine and error boundary

The PDF path requires the PyMuPDF 1.28.2 binding and its declared callable geometry operations. It also requires a usable `FzErrorBase` family with compatible Generic, Argument and System exception classes. Missing or incompatible capabilities fail with `ValueError("native_image_geometry_engine_unsupported")`. PNG arithmetic does not depend on that engine.

Invalid numeric geometry fails with `native_image_geometry_invalid`; empty geometry fails with `native_image_geometry_empty`. At the PDF numeric boundary, the validated native error family becomes the fixed invalid-geometry ValueError with suppressed displayed exception context. Control-flow exceptions remain uncaught. This boundary adds no document parser or general resource supervisor.

## Verification and activation boundary

The dedicated tests retain the byte-pinned original PNG and PDF functions as parity oracles. Synthetic PNG and PDF cases compare actual pixel bytes, bounding boxes and DPI behavior. The repaired suite preserves the original 119-case source prefix and adds 28 native-error controls. The workflow requires all 147 cases and preserves its version, origin, import, network, skip, xfail and deselection guards.

Native rendering occurs in the test fixtures. The planner itself remains numeric. Production image dispatch still needs authorized native source binding, object access, bounded decode and render resources, lifecycle checks and provider-compatible image admission. This module does not activate native images or complete issue44.

See [native_image_geometry.py](../../apps/api/src/ai_pdf_api/modalities/native_image_geometry.py) and [geometry tests](../../apps/api/tests/test_native_image_geometry.py).
