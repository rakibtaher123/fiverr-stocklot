import React, { useState, useEffect } from 'react';

const getSpeciesIcon = (species, title) => {
  // Normalize input to lowercase for comparison
  const normalizedSpecies = (species || '').toLowerCase();
  const normalizedTitle = (title || '').toLowerCase();

  // Check species field first
  if (normalizedSpecies) {
    if (normalizedSpecies.includes('chicken') || normalizedSpecies.includes('poultry') || 
        normalizedSpecies.includes('broiler') || normalizedSpecies.includes('layer') ||
        normalizedSpecies.includes('chick') || normalizedSpecies.includes('hen') ||
        normalizedSpecies.includes('rooster') || normalizedSpecies.includes('cockerel')) {
      return '🐔';
    }
    if (normalizedSpecies.includes('cattle') || normalizedSpecies.includes('cow') || 
        normalizedSpecies.includes('bull') || normalizedSpecies.includes('heifer') ||
        normalizedSpecies.includes('steer') || normalizedSpecies.includes('beef') ||
        normalizedSpecies.includes('dairy')) {
      return '🐄';
    }
    if (normalizedSpecies.includes('goat')) {
      return '🐐';
    }
    if (normalizedSpecies.includes('sheep') || normalizedSpecies.includes('lamb') ||
        normalizedSpecies.includes('ewe') || normalizedSpecies.includes('ram')) {
      return '🐑';
    }
    if (normalizedSpecies.includes('pig') || normalizedSpecies.includes('swine') ||
        normalizedSpecies.includes('hog') || normalizedSpecies.includes('boar') ||
        normalizedSpecies.includes('sow')) {
      return '🐷';
    }
    if (normalizedSpecies.includes('duck') || normalizedSpecies.includes('duckling')) {
      return '🦆';
    }
    if (normalizedSpecies.includes('rabbit') || normalizedSpecies.includes('bunny')) {
      return '🐰';
    }
    if (normalizedSpecies.includes('fish') || normalizedSpecies.includes('aquaculture') ||
        normalizedSpecies.includes('tilapia') || normalizedSpecies.includes('fry') ||
        normalizedSpecies.includes('fingerling')) {
      return '🐟';
    }
    if (normalizedSpecies.includes('ostrich')) {
      return '🦃';
    }
    if (normalizedSpecies.includes('turkey')) {
      return '🦃';
    }
    if (normalizedSpecies.includes('goose') || normalizedSpecies.includes('geese')) {
      return '🦢';
    }
    if (normalizedSpecies.includes('quail')) {
      return '🐦';
    }
    if (normalizedSpecies.includes('guinea') && normalizedSpecies.includes('fowl')) {
      return '🐦';
    }
  }

  // Fallback to title-based detection if species is not available or not matched
  if (normalizedTitle) {
    if (normalizedTitle.includes('chicken') || normalizedTitle.includes('poultry') || 
        normalizedTitle.includes('broiler') || normalizedTitle.includes('layer') ||
        normalizedTitle.includes('chick') || normalizedTitle.includes('hen') ||
        normalizedTitle.includes('rooster') || normalizedTitle.includes('cockerel')) {
      return '🐔';
    }
    if (normalizedTitle.includes('cattle') || normalizedTitle.includes('cow') || 
        normalizedTitle.includes('bull') || normalizedTitle.includes('heifer') ||
        normalizedTitle.includes('steer') || normalizedTitle.includes('beef') ||
        normalizedTitle.includes('dairy') || normalizedTitle.includes('angus') ||
        normalizedTitle.includes('brahman') || normalizedTitle.includes('nguni')) {
      return '🐄';
    }
    if (normalizedTitle.includes('goat') || normalizedTitle.includes('boer')) {
      return '🐐';
    }
    if (normalizedTitle.includes('sheep') || normalizedTitle.includes('lamb') ||
        normalizedTitle.includes('dorper') || normalizedTitle.includes('merino')) {
      return '🐑';
    }
    if (normalizedTitle.includes('pig') || normalizedTitle.includes('swine') ||
        normalizedTitle.includes('hog') || normalizedTitle.includes('boar')) {
      return '🐷';
    }
    if (normalizedTitle.includes('duck') || normalizedTitle.includes('duckling')) {
      return '🦆';
    }
    if (normalizedTitle.includes('rabbit') || normalizedTitle.includes('bunny')) {
      return '🐰';
    }
    if (normalizedTitle.includes('fish') || normalizedTitle.includes('aquaculture') ||
        normalizedTitle.includes('tilapia') || normalizedTitle.includes('fry')) {
      return '🐟';
    }
    if (normalizedTitle.includes('ostrich')) {
      return '🦃';
    }
    if (normalizedTitle.includes('turkey')) {
      return '🦃';
    }
  }

  // Default fallback
  return '🐾';
};

const ImageGallery = ({ media = [], species, title }) => {
  const images = media.filter(m => m.type === 'image');
  const videos = media.filter(m => m.type === 'video');
  const [activeIndex, setActiveIndex] = useState(0);
  const [imageError, setImageError] = useState(false);

  // Reset image error when active index changes
  useEffect(() => {
    setImageError(false);
  }, [activeIndex]);

  const placeholderIcon = getSpeciesIcon(species, title);

  if (!images.length && !videos.length) {
    return (
      <div className="aspect-square bg-gradient-to-br from-emerald-50 to-green-50 rounded-lg flex items-center justify-center">
        <span className="text-9xl" style={{ fontSize: '8rem' }}>
          {placeholderIcon}
        </span>
      </div>
    );
  }

  const allMedia = [...images, ...videos];
  
  return (
    <div className="space-y-3 lg:space-y-4">
      {/* Main Image/Video - Mobile optimized */}
      <div className="aspect-square relative rounded-lg overflow-hidden border border-gray-200 bg-gradient-to-br from-emerald-50 to-green-50">
        {allMedia[activeIndex] && !imageError ? (
          allMedia[activeIndex].type === 'video' ? (
            <video 
              src={allMedia[activeIndex].url} 
              controls 
              className="w-full h-full object-cover"
              poster={allMedia[activeIndex].thumbnail}
            />
          ) : (
            <img 
              src={allMedia[activeIndex].url} 
              alt="Livestock" 
              className="w-full h-full object-cover hover:scale-105 transition-transform duration-300"
              onError={() => setImageError(true)}
            />
          )
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <span className="text-9xl" style={{ fontSize: '8rem' }}>
              {placeholderIcon}
            </span>
          </div>
        )}
        
        {/* Navigation Arrows - Touch friendly */}
        {allMedia.length > 1 && (
          <>
            <button
              onClick={() => setActiveIndex(activeIndex > 0 ? activeIndex - 1 : allMedia.length - 1)}
              className="absolute left-2 lg:left-3 top-1/2 transform -translate-y-1/2 bg-black bg-opacity-50 text-white p-2 lg:p-3 rounded-full hover:bg-opacity-70 transition-all touch-manipulation"
            >
              <svg className="w-4 h-4 lg:w-5 lg:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <button
              onClick={() => setActiveIndex(activeIndex < allMedia.length - 1 ? activeIndex + 1 : 0)}
              className="absolute right-2 lg:right-3 top-1/2 transform -translate-y-1/2 bg-black bg-opacity-50 text-white p-2 lg:p-3 rounded-full hover:bg-opacity-70 transition-all touch-manipulation"
            >
              <svg className="w-4 h-4 lg:w-5 lg:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </>
        )}

        {/* Image counter for mobile */}
        {allMedia.length > 1 && (
          <div className="absolute bottom-2 right-2 bg-black bg-opacity-60 text-white px-2 py-1 rounded text-xs">
            {activeIndex + 1} / {allMedia.length}
          </div>
        )}
      </div>

      {/* Thumbnails - Responsive scrolling */}
      {allMedia.length > 1 && (
        <div className="flex gap-2 lg:gap-3 overflow-x-auto pb-2 -mx-2 px-2">
          {allMedia.map((item, index) => (
            <button
              key={index}
              onClick={() => setActiveIndex(index)}
              className={`relative flex-shrink-0 w-16 h-16 lg:w-20 lg:h-20 rounded-lg overflow-hidden border-2 transition-all touch-manipulation ${
                index === activeIndex 
                  ? 'border-green-500 ring-1 lg:ring-2 ring-green-200' 
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              {item.type === 'video' ? (
                <div className="w-full h-full bg-gray-100 flex items-center justify-center">
                  <svg className="w-4 h-4 lg:w-6 lg:h-6 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd" />
                  </svg>
                </div>
              ) : (
                <img 
                  src={item.url} 
                  alt={`Thumbnail ${index + 1}`}
                  className="w-full h-full object-cover"
                />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default ImageGallery;