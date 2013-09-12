var input_row;
var help_text_row;
var bottom_line;
var top_line;

function hideSpotPriceField(){
    input_row.hide();
    help_text_row.hide();
    bottom_line.hide();
    top_line.hide();
}
function showSpotPriceField(){
    //Always slide
    input_row.show();
    help_text_row.show();
    bottom_line.show();
    top_line.show();
}


window.onload = function(){
    input_row = $('#id_spot_bid_price').parent().parent();
    help_text_row = input_row.next();
    bottom_line = help_text_row.next();
    top_line = input_row.prev();

    
    
    hideSpotPriceField();
    $('#id_pricing_0').click(function(){ //fixed price selected
        hideSpotPriceField(true);
    });
  
    $('#id_pricing_1').click(function(){ //fixed price selected
        showSpotPriceField(true);
    });

}

  