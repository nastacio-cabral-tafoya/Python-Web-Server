var textboxes = document.getElementsByClassName("textbox");

for (let i = 0; i < textboxes.length; i++)
{
	textboxes[i].addEventListener("focusout", function(){
		if (!isblank(textboxes[i].value))
		{
			set_textbox_errorlevel(textboxes[i], 0);
		}
		else
		{
			set_textbox_errorlevel(textboxes[i], 2);
		}
	}, false);
}