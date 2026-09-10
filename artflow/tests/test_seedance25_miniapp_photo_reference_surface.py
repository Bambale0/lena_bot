from pathlib import Path


def test_seedance25_miniapp_reuses_standard_photo_reference_uploader():
    enhancer = Path("webapp/src/lib/seedance25-miniapp-enhancer.ts").read_text(encoding="utf-8")
    generation = Path("webapp/src/features/generation-screen.tsx").read_text(encoding="utf-8")

    # Seedance keeps provider routing automatic, but it must still expose the
    # normal Mini App image uploader with loading/removal state.
    assert "ensurePhotoReferenceSurface" not in enhancer
    assert 'selectedModel?.key === SEEDANCE_25_MODEL' in generation
    assert 'mountedRefs.style.display = ""' in enhancer
    assert 'data-seedance25="imageFiles"' not in enhancer

    assert "onUploadReferenceFiles" in generation
    assert "referenceUploading" in generation
    assert "draft.referenceUrls.map" in generation

    # Uploaded image URLs from the standard uploader remain the authoritative
    # Seedance image-reference transport.
    assert "String(body.image_url || \"\").trim()" in enhancer
    assert "body.reference_urls" in enhancer
    assert "const images = existingImages.slice(0, MAX_IMAGES)" in enhancer


def test_seedance25_miniapp_copy_has_no_first_frame_route():
    enhancer = Path("webapp/src/lib/seedance25-miniapp-enhancer.ts").read_text(encoding="utf-8")
    assert "первый кадр отдельно не используется" in enhancer
    assert "1 фото станет первым кадром" not in enhancer
